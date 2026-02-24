# SecBrain Obsidian Exporter

A scheduled service that exports completed notes from SecBrain's PostgreSQL database to Obsidian markdown files.

## Overview

This exporter:
- Connects to SecBrain's PostgreSQL database (hosted on Zeabur)
- Fetches notes with `status = 'Done'`
- Exports them as properly formatted Obsidian markdown files
- Places files in the `00 Inbox` folder of your Obsidian vault
- Updates note status to `'Archive'` after successful export
- Ensures idempotency and safety (no duplicate exports, atomic file writes)

## Requirements

- Python 3.11 or higher
- Access to SecBrain PostgreSQL database
- Obsidian vault with `00 Inbox` folder

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd secbrain-obsidian-exporter
```

2. Install dependencies:
```bash
pip install -e .
```

Or using pip directly:
```bash
python3 -m pip install -i https://pypi.org/simple psycopg[binary] python-dotenv
```

## Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your configuration:

```bash
# Required
DATABASE_URL=postgresql://user:password@host:port/database
OBSIDIAN_INBOX_PATH=/path/to/obsidian/vault/00 Inbox

# Optional
EXPORT_BATCH_SIZE=100
LOG_LEVEL=INFO
DRY_RUN=false
LOCK_FILE_PATH=/tmp/secbrain-exporter.lock
```

### Configuration Options

- **DATABASE_URL** (required): PostgreSQL connection string for SecBrain
- **OBSIDIAN_INBOX_PATH** (required): Full path to your Obsidian vault's `00 Inbox` folder
- **EXPORT_BATCH_SIZE** (optional): Maximum notes to export per run (default: 100)
- **LOG_LEVEL** (optional): DEBUG, INFO, WARNING, ERROR (default: INFO)
- **DRY_RUN** (optional): Set to `true` to test without writing files (default: false)
- **LOCK_FILE_PATH** (optional): Path for lock file to prevent concurrent runs

## Usage

### Manual Run

```bash
python3 exporter.py
```

Or if installed:
```bash
export-notes
```

### Test with Dry Run

```bash
DRY_RUN=true python exporter.py
```

### Scheduled Execution (Recommended)

#### Using cron (Linux/NAS)

Add to crontab:
```bash
# Run every hour
0 * * * * cd /path/to/secbrain-obsidian-exporter && /usr/bin/python3 exporter.py >> /var/log/secbrain-export.log 2>&1
```

#### Using systemd timer (Linux)

Create `/etc/systemd/system/secbrain-export.service`:
```ini
[Unit]
Description=SecBrain Obsidian Exporter
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/secbrain-obsidian-exporter
EnvironmentFile=/path/to/secbrain-obsidian-exporter/.env
ExecStart=/usr/bin/python3 /path/to/secbrain-obsidian-exporter/exporter.py
User=your-user
```

Create `/etc/systemd/system/secbrain-export.timer`:
```ini
[Unit]
Description=SecBrain Exporter Timer

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable secbrain-export.timer
sudo systemctl start secbrain-export.timer
```

## Output Format

Each exported note becomes a markdown file with:

**Filename:** `YYYYMMDD-HHmm__<note-id>.md`

**Content:**
```markdown
---
id: "note-id"
createdAt: "2026-02-24T10:30:00Z"
source: "SecBrain"
exportedAt: "2026-02-24T12:00:00Z"
status: "Done"
---

[Note markdown content here]
```

## Safety & Idempotency

- **Atomic writes**: Files are written to a temp file, fsynced, then renamed
- **No duplicate exports**: Existing files are skipped
- **Safe status updates**: Notes are only marked as `'Archive'` after successful file write
- **Concurrent execution prevention**: Lock file prevents multiple instances from running simultaneously

## Exit Codes

- `0`: Success
- `1`: Configuration error
- `2`: Database error
- `3`: Filesystem error
- `4`: Lock error (another instance is running)

## Logging

The exporter logs:
- Number of notes fetched
- Number of notes exported
- Number of notes skipped (already exist)
- Number of failures

Example output:
```
2026-02-24 12:00:00 - __main__ - INFO - Starting SecBrain to Obsidian export
2026-02-24 12:00:01 - __main__ - INFO - Connected to database
2026-02-24 12:00:01 - __main__ - INFO - Fetched 5 notes with status='Done'
2026-02-24 12:00:02 - __main__ - INFO - Created: 20260224-1000__abc123.md
2026-02-24 12:00:02 - __main__ - INFO - Export complete - Fetched: 5, Exported: 5, Skipped: 0, Failed: 0
```

## Troubleshooting

### "Lock file exists" error
Another instance may be running. Check for running processes or remove the lock file if you're certain no other instance is active:
```bash
rm /tmp/secbrain-exporter.lock
```

### "OBSIDIAN_INBOX_PATH does not exist"
Ensure the `00 Inbox` folder exists in your Obsidian vault and the path is correct.

### Database connection errors
- Verify `DATABASE_URL` is correct
- Check network connectivity to Zeabur
- Ensure database credentials are valid

## Development

For development and testing:

1. Set up a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
```

2. Install in development mode:
```bash
pip install -e .
```

3. Run with dry-run mode:
```bash
DRY_RUN=true LOG_LEVEL=DEBUG python exporter.py
```

## License

[Specify your license here]

## Contributing

[Specify contribution guidelines if applicable]
