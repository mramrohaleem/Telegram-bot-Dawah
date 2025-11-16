# Telegram Media Archiver Bot – System Architecture

## 1. Purpose & Scope

This project is a **Telegram bot** that:

- Receives links to **video/audio content** (primarily YouTube, but also other sites such as Facebook, Archive.org, and Islamic lecture sites like Way2Allah).
- Downloads the requested media on a **server**, converts it to a Telegram-friendly format, and sends it back to the user **ready to play** (not just as a raw file).
- Optionally **archives** selected media on the server in an organized way for later reuse, while cleaning up temporary files safely.

The system is designed to be:

1. **Stable and predictable** (first priority).
2. **Easy to debug** through rich diagnostic logging and job history.
3. **Cleanly architected** and easy to extend.
4. **Fast enough** for typical usage on a single VPS (no over-engineering).
5. **Operated and evolved via AI-assisted coding** (user is not a programmer).

The bot is **not** designed to:

- Serve millions of users or huge global scale.
- Be a distributed microservice system.
- Break or bypass DRM or any protected content mechanisms.

---

## 2. Design Priorities (in order)

1. **Stability & correctness**  
   - Jobs should not disappear, duplicate, or get stuck silently.
   - State transitions must be safe and strictly controlled.

2. **Observability & debugging**  
   - Every job has a clear event timeline.
   - Logs are structured and searchable.
   - Failures are categorized with meaningful error types.

3. **Clean architecture & modularity**  
   - Separate concerns (Telegram vs orchestration vs download vs storage).
   - Allow future changes (e.g., add a new source) in one module only.

4. **Performance & resource safety**  
   - Reasonable throughput on a single server.
   - Respect CPU, memory, and disk limits.
   - No unbounded queues or unbounded file growth.

5. **Features / UX sugar**  
   - Nice interaction flow with the user.
   - Archive mode, rename options, etc.

In any trade-off, follow this priority order.

---

## 3. Tech Stack

### 3.1 Language & Runtime

- **Language:** Python 3.x
- **Style:** Async-first where relevant (workers, bot).
- The user will rely heavily on AI tools; code must be:
  - Clear, well-structured, and as simple as practical.
  - Avoid extremely clever or obscure patterns.

### 3.2 Major Libraries

- **Telegram:**
  - [`python-telegram-bot`](https://python-telegram-bot.org/) (async `Application` API).

- **Downloader:**
  - [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) used as a **Python library**, not just CLI.
  - Wrapped in a dedicated `YouTubeDownloader` module.

- **Database & ORM:**
  - DB: **SQLite** for the initial version (single-file, zero-setup).
  - ORM: **SQLAlchemy** (or SQLModel if simpler), but must be explicit and clear.

- **Logging:**
  - Python’s built-in `logging` module.
  - Structured logs (JSON-like) written to stdout (and optionally file).

- **Config:**
  - Environment variables for secrets (e.g., Telegram bot token).
  - A simple config module or `config.yaml` for non-secret settings.

No microservices, no Kubernetes, no extra infrastructure unless explicitly added later.

---

## 4. High-level Architecture

Single process, single codebase, multiple logical layers:

1. **Telegram Layer (`bot/`)**
   - Handles Telegram updates (messages, commands).
   - Validates and parses user input (URLs, options).
   - Calls orchestration services to create jobs and query status.
   - Never directly touches download logic or filesystem.

2. **Orchestration / Domain Layer (`core/`)**
   - The “brain” of the system.
   - Manages:
     - Job creation and validation.
     - Job state transitions.
     - Scheduling jobs to workers (queue logic).
     - Retry, timeout, and recovery policies.
     - Limits (per-user / per-chat / global).

3. **Download Engine (`download/`)**
   - Specialized modules per source type.
   - Responsible for:
     - Fetching metadata.
     - Selecting formats.
     - Performing the download (using `yt-dlp` or appropriate logic).
     - Classifying errors by type.

4. **Storage & Persistence (`storage/`)**
   - Database models and repositories (jobs, events, auth profiles, chat settings).
   - File storage layout:
     - Temporary downloads.
     - Archived files.

5. **Config & Logging (`config/`, `logging/`)**
   - Central configuration definitions and defaults.
   - Centralized logging setup (JSON format, unified fields).

Each layer depends **only downward** (Telegram → core → download/storage), never the other way.

---

## 5. Core Concepts & Data Model

### 5.1 Job

Represents a single media download request.

**Fields (conceptual):**

- `id` (integer or UUID)
- `url` (string)
- `source_type` (enum `SourceType` – see below)
- `job_type` (enum `JobType` – `VIDEO` or `AUDIO`)
- `requested_quality` (string, e.g. `"best"`, `"720p"`, `"audio_128"`)
- `status` (enum `JobStatus` – see Section 6)
- `retry_count` (integer)
- `job_key` (string hash for dedup: based on `source_type + normalized_url + job_type + normalized_quality`)
- `auth_profile_id` (string, optional)
- `user_id` (Telegram user id)
- `chat_id` (Telegram chat id)
- `created_at`, `updated_at` (timestamps)
- `final_title` (string, possibly user-customized)
- `file_path` (string path on disk once completed)
- `error_type` (enum `ErrorType`, nullable)
- `error_message` (short text, nullable)

### 5.2 Job Events

Timeline of everything important that happened to a job.

**Fields:**

- `id`
- `job_id`
- `event_type` (string/enum; e.g. `JOB_CREATED`, `STATUS_CHANGED`, `DOWNLOAD_STARTED`, `DOWNLOAD_FAILED`, `TELEGRAM_SEND_FINISHED`, etc.)
- `data` (JSON blob with contextual info)
- `created_at`

### 5.3 Auth Profiles

Represents authentication context per source (e.g., which cookies file to use).

**Fields:**

- `id` (e.g. `"yt_main"`, `"yt_guest"`, `"fb_main"`)
- `source_type` (`YOUTUBE`, `FACEBOOK`, ...)
- `cookie_file_path` (optional; path to cookies file on disk)
- `status` (enum: `ACTIVE`, `DEGRADED`, `DISABLED`)
- `failure_count_recent` (int)
- `last_success_at` (timestamp, nullable)
- `last_failure_at` (timestamp, nullable)

The actual *cookie/token contents* are **never** logged or stored in DB directly. Only the file path and profile id are stored.

### 5.4 Chat / User Settings

Per chat or user, we may store:

- `chat_id` / `user_id`
- `archive_mode` (bool)
- `default_job_type` (default audio or video)
- `default_quality`
- `rate_limit_counters` (or stored elsewhere)
- `is_admin` flag for admin commands

---

## 6. Job State Machine

### 6.1 Statuses

`JobStatus` enum:

- `PENDING` – created, not yet queued for worker.
- `QUEUED` – acknowledged by scheduler, waiting for a worker slot.
- `RUNNING` – currently being processed by a worker.
- `COMPLETED` – successfully downloaded and (optionally) sent to user.
- `FAILED` – finished with an unrecoverable error.

Other internal markers (used as `error_type` or events) can denote:
- `FAILED_TIMEOUT`
- `FAILED_STALE`
- `FAILED_MAX_RETRIES`
but the primary `status` remains `FAILED`.

### 6.2 Allowed Transitions

Only allow the following transition paths:

- `PENDING` → `QUEUED`
- `QUEUED` → `RUNNING`
- `RUNNING` → `COMPLETED`
- `RUNNING` → `FAILED`
- `PENDING` → `FAILED` (e.g. validation error)
- `QUEUED` → `FAILED` (e.g. job cancelled/invalid)

All transitions must go through a **single** function, e.g.:

```text
transition_status(job_id, from_status, to_status, metadata)
Rules:

Check that from_status matches the current DB value; otherwise log an internal logic error.

Refuse illegal transitions and log them.

Log a STATUS_CHANGED event with both old and new statuses.

No direct modifications like job.status = "COMPLETED" outside this central function.

7. Job Lifecycle (High-Level)
User submits URL via Telegram message.

Telegram handler:

Detects URL.

Detects source_type.

Chooses or asks for job_type (audio/video) and quality.

Orchestrator:

Checks dedup (existing job_key).

Creates new Job (or links to existing).

Logs JOB_CREATED.

Puts job into PENDING.

Scheduler:

Periodically scans PENDING jobs.

Moves them to QUEUED and assigns to worker when capacity allows.

Worker:

Transitions QUEUED → RUNNING.

Calls Download Engine with context.

On success:

Stores final file path.

Transitions RUNNING → COMPLETED.

On failure:

Applies retry policy or final FAILED.

Telegram layer:

On COMPLETED, sends the media to user (audio/video ready to play).

If job not archived, the file may be scheduled for deletion later.

Recovery:

On startup, a recovery routine handles stale RUNNING jobs and ensures they are either retried or marked as failed, so nothing is “stuck forever”.

8. Download Engine
8.1 Source Types & Router
Enum SourceType:

YOUTUBE

FACEBOOK

ARCHIVE (Archive.org)

TARIQ_ALLAH (Way2Allah / IslamWay style sites)

GENERIC (fallback for direct media URLs or unknown sites)

A router function:

text
نسخ الكود
detect_source_type(url) -> SourceType
Then another function:

text
نسخ الكود
get_downloader_for_source(source_type) -> BaseDownloader
8.2 BaseDownloader Interface
All downloaders implement:

fetch_metadata(url, context) -> MetadataResult

download(url, options, context) -> DownloadResult

Where:

MetadataResult (conceptual):

success: bool

title: Optional[str]

duration_seconds: Optional[int]

available_video_formats: List[...]

available_audio_formats: List[...]

raw_info: dict (for debugging; not necessarily logged fully)

DownloadResult:

success: bool

file_path: Optional[str]

error_type: Optional[ErrorType]

error_message: Optional[str]

metadata: dict (e.g. final title, thumbnail url, duration)

8.3 Error Classification
ErrorType enum (examples):

NETWORK_ERROR – timeouts, DNS, connection issues.

HTTP_ERROR – non-2xx HTTP status (with status code).

AUTH_ERROR – cookies/credentials invalid or insufficient.

RATE_LIMIT – “too many requests” patterns, 429, etc.

EXTRACTOR_ERROR – site layout changed, extractor logic broken.

EXTRACTOR_UPDATE_REQUIRED – known patterns from yt-dlp indicating update needed.

GEO_BLOCK – region-locked content.

SIZE_LIMIT – estimated or actual file too large for Telegram or configured limits.

FORMAT_NOT_FOUND – no suitable format for requested type/quality.

PARSER_ERROR – HTML parsing failed (for sites like Way2Allah).

PROTECTED_CONTENT – content protected/DRM, cannot be processed.

UNSUPPORTED_SOURCE – site not supported by any downloader.

UNKNOWN – anything that doesn’t fit the above.

Every failed DownloadResult must set an error_type.

8.4 Download Pipeline (Per Job)
For each job, the worker runs a structured pipeline:

METADATA_FETCH

Use downloader to fetch metadata.

If fails → METADATA_FETCH_FAILED with error_type.

CAPABILITY_CHECK

Determine if there is at least one suitable format:

matches job_type (audio/video),

meets quality constraints,

estimated size within limits.

If not → fail early with FORMAT_NOT_FOUND or SIZE_LIMIT.

DOWNLOAD

Invoke downloader’s download.

Use correct auth_profile (cookies) if configured for that source.

Apply internal timeouts and concurrency limits.

POSTPROCESS

If necessary, convert to:

Telegram-friendly video (e.g. MP4 with supported codecs).

Telegram audio / voice format (e.g. audio with thumbnail and title).

OUTPUT_VALIDATE

Check:

File exists.

File size <= Telegram max and configured max.

If not → SIZE_LIMIT or UNKNOWN fail.

Each step logs events like:

METADATA_FETCH_STARTED

METADATA_FETCH_FINISHED

DOWNLOAD_STARTED

DOWNLOAD_FINISHED

POSTPROCESS_FINISHED

OUTPUT_VALIDATED

8.5 YouTubeDownloader
Special handling for YouTube:

Use yt-dlp via Python API.

fetch_metadata:

Use yt-dlp “info extraction” without full download.

Extract:

title

duration

available formats (video/audio).

Format Selection:

Normalize requested quality ("best", "720p", "480p", "audio_128", etc.).

Filter formats:

by type (video/audio),

by quality and codec,

by estimated size (duration × bitrate), if possible.

Choose “sensible” default if user did not specify quality (e.g. 720p or medium VBR audio).

Auth Profiles:

Use auth_profile_id → resolve cookie_file_path.

Attempt download with primary profile (yt_main by default).

On AUTH_ERROR or specific 403/401 patterns:

Optionally try fallback profiles (yt_guest, yt_alt) based on config.

Track per-profile:

failure_count_recent

last_success_at

If many consecutive AUTH_ERRORs for a profile:

mark profile DEGRADED and avoid it until refreshed.

EXTRACTOR errors:

Inspect yt-dlp exceptions/messages.

Map known patterns to EXTRACTOR_UPDATE_REQUIRED or EXTRACTOR_ERROR.

8.6 FacebookDownloader
Uses cookies via auth_profile (typically required).

Handles:

metadata fetch (if supported by downloader),

direct URL resolution for video,

error classification:

permission errors → AUTH_ERROR or PROTECTED_CONTENT.

404 → HTTP_ERROR.

8.7 ArchiveDownloader (Archive.org)
Use HTTP HEAD to determine:

file size,

content type (audio/video).

If content seems appropriate (audio/video), download directly.

If file too large:

Fail with SIZE_LIMIT before full download.

8.8 TariqAllahDownloader (Way2Allah / similar)
Either:

use yt-dlp if it supports the site, or

parse HTML to find <audio> or direct download links.

Fail with PARSER_ERROR if layout changes break the parser.

Then delegate final download to a generic HTTP downloader.

8.9 GenericDownloader
For direct media URLs (e.g. .mp3, .mp4):

HEAD for size/type.

Download with streaming.

Restricted to safe protocols (see Security section).

9. Queue, Workers, Retry & Recovery
9.1 Queue Model
Jobs stored in DB with status.

Scheduler component periodically:

checks jobs with status = PENDING or QUEUED,

respects:

max_parallel_jobs (global),

max_parallel_jobs_per_source (optional),

moves jobs to QUEUED then RUNNING via the state machine.

9.2 Worker Model
Implemented as async tasks within the same process.

Each worker:

Receives a job id.

Transitions status QUEUED → RUNNING.

Logs WORKER_ASSIGNED and DOWNLOAD_STARTED.

Executes download pipeline.

On success:

Moves to COMPLETED, logs JOB_COMPLETED.

On failure:

Applies retry policy.

For final failure, logs JOB_FAILED with error_type.

9.3 Retries
Policy:

Track retry_count per job.

Configurable max_retries (e.g. 3).

Retry allowed only for:

NETWORK_ERROR

possibly RATE_LIMIT (with backoff)

No retry for:

AUTH_ERROR

FORMAT_NOT_FOUND

SIZE_LIMIT

PROTECTED_CONTENT

UNSUPPORTED_SOURCE

EXTRACTOR_UPDATE_REQUIRED (until manual fix).

Use basic exponential backoff for retries (e.g. 1m, 5m, 15m).

Log events:

RETRY_SCHEDULED

RETRY_SKIPPED (when error not retryable)

MAX_RETRIES_REACHED

9.4 Timeouts & Stale Jobs
Per stage timeouts:

metadata fetch timeout.

download timeout.

post-process timeout.

Overall job timeout (e.g. 30–40 minutes for extreme cases).

On startup:

Recovery routine:

For jobs in RUNNING for longer than configured threshold:

Mark as FAILED_STALE and FAILED, or

Optionally reschedule with retry_count + 1, depending on policy.

Log:

JOB_RECOVERED_STALE

STALE_JOB_MARKED_FAILED

10. Storage Layout & Archive Mode
10.1 Paths
Configurable root paths:

TMP_ROOT – e.g. /tmp/telegram_downloader

ARCHIVE_ROOT – e.g. /data/telegram_archive

All file paths must be created using dedicated functions in a StorageService:

get_tmp_path_for_job(job_id)

get_archive_path(job, metadata)

No hand-built paths scattered in the code.

10.2 Archive Mode
Per-chat or per-job option:

If archive_mode = true for the chat:

On successful job:

move the file from TMP_ROOT to ARCHIVE_ROOT in an organized structure (e.g. by source, date, chat id).

If archive_mode = false:

File remains in TMP_ROOT only until cleanup.

Chat-level commands:

/archive_on

/archive_off

Persisted in chat_settings.

10.3 Cleanup
Scheduled cleanup routine:

Deletes tmp files older than a configured age (e.g. 24–72 hours) for jobs not archived.

Ensures disk usage doesn’t grow unbounded.

11. Security & Safety (Technical)
11.1 URL & Protocol Restrictions
Allow only URLs with:

https:// (and optionally http:// if needed).

Reject:

file://, ftp://, mailto:, and any unknown schemes.

Reject or treat as UNSUPPORTED_SOURCE any domain not in:

Supported list (youtube.com, youtu.be, facebook.com, fb.watch, archive.org, configured Islamic sites, etc.), or

Generic direct media URLs when obviously safe (e.g. .mp3, .mp4 with correct MIME).

11.2 Path Sanitization
Filenames derived from metadata or user input must:

be sanitized to remove dangerous characters: .., /, \, :, etc.

be trimmed to reasonable length.

A single helper function:

sanitize_title_to_filename(title) -> safe_filename

All storages must use this helper.

11.3 Limits
Global:

max_parallel_jobs

max_queue_length

Per-user:

max active jobs at once.

max jobs per time window (e.g. per hour).

Per-chat:

similar limits to protect from abuse.

When rejecting a job due to limits, respond with a clear Telegram message and log the reason.

11.4 Secrets Handling
Telegram bot token and any other secrets must come from environment variables.

Never log tokens, cookies, or auth headers.

Logs may only reference auth_profile_id and cookie_file_path, not contents.

12. Logging & Observability
12.1 Logger Setup
One central logger factory:

get_logger(name)

Output format:

JSON-like lines, each including at least:

level

timestamp

logger

message

context (dict)

12.2 Required Context Fields
For any job-related log:

job_id

user_id (if available)

chat_id (if available)

source_type

stage (one of: BOT, ORCHESTRATOR, QUEUE, WORKER, DOWNLOAD, TELEGRAM_SEND)

url_domain

auth_profile_id (if applicable)

downloader_name / downloader_version (for download logs)

error_type (if error)

http_status (if relevant)

12.3 Must-log Events per Job
At minimum, for each job:

JOB_CREATED

STATUS_CHANGED (each transition)

METADATA_FETCH_STARTED

METADATA_FETCH_FINISHED (or METADATA_FETCH_FAILED)

DOWNLOAD_STARTED

DOWNLOAD_FINISHED (or DOWNLOAD_FAILED)

POSTPROCESS_FINISHED (if applicable)

OUTPUT_VALIDATED

TELEGRAM_SEND_STARTED

TELEGRAM_SEND_FINISHED (or TELEGRAM_SEND_FAILED)

RETRY_SCHEDULED / RETRY_SKIPPED

JOB_COMPLETED or JOB_FAILED

All of these must create both:

A job_events row.

A log line.

12.4 Debug / Production Modes
Default: INFO level logs for main events.

DEBUG mode:

can be enabled via config or admin command.

Should add more details for selected jobs (by job_id) or selected users, without flooding logs for everything.

13. Admin & Debug Interfaces
Exposed via Telegram commands (restricted to admin users):

/health

Show:

count of jobs by status,

count of running jobs per source,

recent error counts by error_type.

/queue

Show summary of current PENDING / QUEUED / RUNNING jobs.

/job <id>

Show:

job status,

source type,

error info,

last few job events.

/debug_on <job_id> / /debug_off <job_id> (optional)

Mark a specific job to log at DEBUG level.

All admin commands must check is_admin or a configured list of admin user ids.

14. Configuration & Feature Flags
A central config module or file defines:

Paths:

TMP_ROOT

ARCHIVE_ROOT

Limits:

max_parallel_jobs

max_parallel_jobs_per_source

max_queue_length

max_jobs_per_user_per_hour

max_jobs_per_chat_per_hour

max_file_size_bytes (overall or per media type)

Timeouts:

metadata_timeout_seconds

download_timeout_seconds

postprocess_timeout_seconds

job_stale_threshold_seconds

Retries:

max_retries

retry_backoff_pattern (e.g. incremental delays)

Modes:

maintenance_mode (on/off – reject new jobs)

debug_mode (global debug; use with care)

All such values must be configurable and not hard-coded inside scattered code.

15. Implementation Phases (for AI Coding Agents)
When implementing, follow a phased approach. Each phase should be implemented, tested, and stabilized before moving to the next:

Phase 0 – Project skeleton

Create folder structure, config, logging setup.

Phase 1 – Domain & DB schema

Implement Job, JobEvents, AuthProfiles models and repository/service.

Phase 2 – State machine & logging

Implement transition_status and event logging.

Phase 3 – Minimal Telegram bot (/ping)

Connect to Telegram, verify basic operations.

Phase 4 – Create jobs from Telegram messages

Parse URLs, detect source type, create job entries only.

Phase 5 – Internal queue & worker loop (mock processing)

Implement scheduler + workers with fake work.

Phase 6 – Download Engine abstraction (no real yt-dlp yet or minimal)

Implement BaseDownloader, DownloadResult, error classification skeleton.

Phase 7 – Real YouTubeDownloader using yt-dlp

Metadata, format selection, real download.

Phase 8 – Downloaders for other sources (Facebook, Archive, TariqAllah, Generic)

Implement and integrate.

Phase 9 – Archive mode, storage layout & cleanup

Implement archive/move logic, tmp cleanup.

Phase 10 – Admin/debug commands

/health, /queue, /job.

Phase 11 – Retries, timeouts, limits, stale recovery

Implement full policies.

Phase 12 – Packaging / deployment basics

Dockerfile, README, env config.

Each phase’s prompt to an AI coding agent must:

Reference this ARCHITECTURE.md.

Clearly state which phase is being implemented.

Forbid modifying unrelated layers unless necessary.

16. Non-Goals / Constraints
No microservices: everything is in one codebase and one main process for now.

No advanced metrics stack required; logs + simple admin commands are enough initially.

No automated tests required initially, but core logic (state machine, error classification, format selection, filename sanitization) should be implemented in a way that is testable later.
