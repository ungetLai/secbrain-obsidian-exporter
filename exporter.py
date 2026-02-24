#!/usr/bin/env python3
"""
SecBrain to Obsidian Exporter
Exports notes with status='Done' from PostgreSQL to Obsidian markdown files.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import tempfile

import psycopg
from dotenv import load_dotenv


# Exit codes (as per SKILL.md section 11)
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_DB_ERROR = 2
EXIT_FS_ERROR = 3
EXIT_LOCK_ERROR = 4


class Config:
    """Configuration loaded from environment variables."""
    
    def __init__(self):
        load_dotenv()
        
        # Required
        self.database_url = os.getenv("DATABASE_URL")
        self.obsidian_inbox_path = os.getenv("OBSIDIAN_INBOX_PATH")
        
        # Optional
        self.export_batch_size = int(os.getenv("EXPORT_BATCH_SIZE", "100"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.dry_run = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")
        self.lock_file_path = os.getenv("LOCK_FILE_PATH", "/tmp/secbrain-exporter.lock")
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate required configuration."""
        if not self.database_url:
            return False, "DATABASE_URL is required"
        if not self.obsidian_inbox_path:
            return False, "OBSIDIAN_INBOX_PATH is required"
        
        # Check if inbox path exists
        inbox = Path(self.obsidian_inbox_path)
        if not inbox.exists():
            return False, f"OBSIDIAN_INBOX_PATH does not exist: {self.obsidian_inbox_path}"
        if not inbox.is_dir():
            return False, f"OBSIDIAN_INBOX_PATH is not a directory: {self.obsidian_inbox_path}"
        
        return True, None


class FileLock:
    """Simple file-based lock for preventing concurrent execution."""
    
    def __init__(self, lock_path: str):
        self.lock_path = Path(lock_path)
        self.lock_file = None
    
    def __enter__(self):
        if self.lock_path.exists():
            raise RuntimeError(f"Lock file exists: {self.lock_path}. Another instance may be running.")
        
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(str(os.getpid()))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_path.exists():
            self.lock_path.unlink()


class ObsidianExporter:
    """Main exporter class."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def generate_filename(self, note_id: str, created_at: datetime) -> str:
        """Generate filename per SKILL.md section 4.2: YYYYMMDD-HHmm__<id>.md"""
        timestamp = created_at.strftime("%Y%m%d-%H%M")
        return f"{timestamp}__{note_id}.md"
    
    def generate_frontmatter(self, note_id: str, created_at: datetime) -> str:
        """Generate YAML frontmatter per SKILL.md section 4.3"""
        export_time = datetime.utcnow().isoformat() + "Z"
        created_iso = created_at.isoformat() + "Z" if created_at.tzinfo is None else created_at.isoformat()
        
        return f"""---
id: "{note_id}"
createdAt: "{created_iso}"
source: "SecBrain"
exportedAt: "{export_time}"
status: "Done"
---
"""
    
    def write_markdown_file(self, note_id: str, created_at: datetime, markdown: str) -> bool:
        """
        Safely write markdown file per SKILL.md section 6:
        Write temp file -> fsync -> rename
        """
        inbox_path = Path(self.config.obsidian_inbox_path)
        filename = self.generate_filename(note_id, created_at)
        target_path = inbox_path / filename
        
        # Idempotency check (SKILL.md section 5)
        if target_path.exists():
            self.logger.info(f"File already exists, skipping: {filename}")
            return True
        
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] Would create: {filename}")
            return True
        
        # Generate content
        frontmatter = self.generate_frontmatter(note_id, created_at)
        content = frontmatter + "\n" + markdown.strip() + "\n"
        
        # Safe write: temp file -> fsync -> rename
        try:
            # Write to temp file in the same directory (for atomic rename)
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                newline='\n',
                dir=inbox_path,
                delete=False,
                suffix='.tmp'
            ) as tmp_file:
                tmp_file.write(content)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
                temp_path = tmp_file.name
            
            # Atomic rename
            os.replace(temp_path, target_path)
            self.logger.info(f"Created: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write {filename}: {e}")
            # Clean up temp file if it exists
            if 'temp_path' in locals():
                try:
                    os.unlink(temp_path)
                except:
                    pass
            return False
    
    def archive_note(self, conn, note_id: str) -> bool:
        """
        Update note status to 'Archive' per SKILL.md section 3.4
        Only called after successful file write.
        """
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] Would archive note: {note_id}")
            return True
        
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE "Note" SET status = 'Archive' 
                       WHERE id = %s AND status = 'Done'""",
                    (note_id,)
                )
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to archive note {note_id}: {e}")
            conn.rollback()
            return False
    
    def fetch_done_notes(self, conn):
        """
        Fetch notes eligible for export per SKILL.md section 3.3:
        - status = 'Done'
        - markdown IS NOT NULL
        - TRIM(markdown) <> ''
        """
        query = """
            SELECT id, "createdAt", markdown
            FROM "Note"
            WHERE status = 'Done'
              AND markdown IS NOT NULL
              AND TRIM(markdown) <> ''
            ORDER BY "createdAt"
            LIMIT %s
        """
        
        with conn.cursor() as cur:
            cur.execute(query, (self.config.export_batch_size,))
            return cur.fetchall()
    
    def run(self) -> int:
        """Main execution logic."""
        self.logger.info("Starting SecBrain to Obsidian export")
        
        fetched = 0
        exported = 0
        skipped = 0
        failed = 0
        
        try:
            # Connect to database
            with psycopg.connect(self.config.database_url) as conn:
                self.logger.info("Connected to database")
                
                # Fetch eligible notes
                notes = self.fetch_done_notes(conn)
                fetched = len(notes)
                self.logger.info(f"Fetched {fetched} notes with status='Done'")
                
                # Process each note
                for note in notes:
                    note_id, created_at, markdown = note
                    
                    # Write markdown file
                    if self.write_markdown_file(note_id, created_at, markdown):
                        # Only archive if file write succeeded
                        if self.archive_note(conn, note_id):
                            exported += 1
                        else:
                            failed += 1
                            self.logger.warning(f"File written but archive failed for: {note_id}")
                    else:
                        failed += 1
        
        except psycopg.Error as e:
            self.logger.error(f"Database error: {e}")
            return EXIT_DB_ERROR
        except OSError as e:
            self.logger.error(f"Filesystem error: {e}")
            return EXIT_FS_ERROR
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return EXIT_DB_ERROR
        
        # Log summary (SKILL.md section 10)
        self.logger.info(
            f"Export complete - "
            f"Fetched: {fetched}, "
            f"Exported: {exported}, "
            f"Skipped: {skipped}, "
            f"Failed: {failed}"
        )
        
        return EXIT_SUCCESS


def setup_logging(level: str):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Entry point."""
    # Load and validate config
    config = Config()
    valid, error = config.validate()
    
    if not valid:
        print(f"Configuration error: {error}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    
    # Setup logging
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)
    
    # Acquire lock to prevent concurrent execution (SKILL.md section 8)
    try:
        with FileLock(config.lock_file_path):
            exporter = ObsidianExporter(config)
            return exporter.run()
    except RuntimeError as e:
        logger.error(f"Lock error: {e}")
        return EXIT_LOCK_ERROR


if __name__ == "__main__":
    sys.exit(main())
