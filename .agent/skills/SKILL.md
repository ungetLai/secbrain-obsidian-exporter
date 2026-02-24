# SKILL.md --- secbrain-obsidian-exporter

> Purpose: This Skill defines the non-negotiable rules, logic, and
> implementation contract for the project
> **secbrain-obsidian-exporter**. Use this document as the single source
> of truth when working with Copilot (or any AI/dev). The implementation
> MUST follow this spec unless this file is explicitly updated.

------------------------------------------------------------------------

## 0) One-sentence Summary

Run a scheduled service on NAS that connects to the Zeabur PostgreSQL
used by SecBrain, exports `Note` records with `status = Done` into real
Obsidian Markdown files placed into the NAS vault folder `00 Inbox`, and
then safely transitions those notes to `Archive` only after the file
write succeeds.

## 1) Goals

### 1.1 Primary Goals

-   Periodically export completed notes from PostgreSQL to `.md` files.
-   Output files must be immediately usable by Obsidian (frontmatter +
    markdown body).
-   Guarantee idempotency: the same note must not be exported twice.
-   Guarantee safety: never mark a note as archived unless the
    corresponding file is durably written.

### 1.2 Non-Goals

-   Not a realtime sync.
-   Not bidirectional sync.
-   No UI. CLI only.

## 2) System Context

### 2.1 Upstream

-   SecBrain stores inspirations/ideas in PostgreSQL.
-   Another agent converts raw ideas into `Note.markdown` and sets
    `Note.status = Done`.

### 2.2 This Project

-   Runs on NAS
-   Pulls `Done` notes from Zeabur PostgreSQL
-   Writes `.md` into Obsidian vault folder `00 Inbox`
-   Updates DB status from `Done` -\> `Archive` when successful

## 3) Data Contract (Database)

### 3.1 Source Table/Model

-   `Note`

### 3.2 Required Fields

-   `id`
-   `createdAt`
-   `markdown`
-   `status`

### 3.3 Eligibility Rules

-   `status = 'Done'`
-   `markdown IS NOT NULL`
-   `TRIM(markdown) <> ''`

### 3.4 Post-export State Transition

-   `UPDATE Note SET status='Archive' WHERE id=? AND status='Done'`

## 4) Output Contract (Obsidian Files)

### 4.1 Target Folder

-   `OBSIDIAN_INBOX_PATH` -\> local NAS path to `00 Inbox`

### 4.2 File Naming

-   `YYYYMMDD-HHmm__<id>.md`

### 4.3 File Content (MUST)

``` yaml
---
id: "<note-id>"
createdAt: "<ISO8601>"
source: "SecBrain"
exportedAt: "<ISO8601>"
status: "Done"
---
```

Then:

``` md
<note.markdown>
```

### 4.4 Encoding

-   UTF-8, newline normalized to `\n`{=tex}

## 5) Idempotency

-   Do not export the same note twice.
-   If file already exists, treat as exported.

## 6) Safety

-   Write temp file -\> fsync -\> rename
-   Only archive after rename success

## 7) Execution

-   CLI program triggered by cron/systemd timer

## 8) Concurrency

-   Use lockfile or DB row locking

## 9) Configuration

Required env: - DATABASE_URL - OBSIDIAN_INBOX_PATH

Optional: - EXPORT_BATCH_SIZE - LOG_LEVEL - DRY_RUN - LOCK_FILE_PATH

## 10) Logging

-   Log counts of fetched/exported/skipped/failed

## 11) Exit Codes

-   0 success
-   1 config error
-   2 DB error
-   3 FS error
-   4 lock error

## 12) Test Plan

-   Unit: filename, frontmatter
-   Integration: Done -\> md -\> Archive
-   Idempotency: rerun safe

## 13) Implementation Notes

-   Python 3.11+
-   psycopg3 or asyncpg
-   python-dotenv
-   pyproject.toml

## 14) Copilot Instructions

-   Sections 3--6 are strict contracts.
-   Do not change formats unless updating this file.

## 15) Future Enhancements

-   Multiple vaults
-   Hash-based change detection
-   Metrics output
