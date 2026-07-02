# BookBuddARR

BookBuddARR bridges [BookBuddy](https://www.kimicoapps.com/bookbuddy/) CSV exports into self-hosted book and audiobook workflows.

It is designed for a simple loop:

1. Export your library from BookBuddy as CSV.
2. Run `bookbuddarr ingest`.
3. Keep a persistent local registry of books already processed.
4. Produce queues for only the newly scanned books.
5. Review/import those queues into Readarr and audiobook discovery tools.

BookBuddARR is approval-gated automation. It creates structured queues, searches through your configured Prowlarr indexers, stores review state, and can hand approved or high-confidence eligible releases to your configured download/import stack. Ambiguous language matches and multipart releases stay blocked for review.

## Required Stack

BookBuddARR is designed to sit next to an Arr-style media stack. The target production flow expects:

- Docker or Docker Compose.
- Prowlarr for aggregate indexer search and release grabbing.
- qBittorrent for torrent download handoff.
- Optional SABnzbd or NZBGet for Usenet handoff.
- Audiobookshelf for the final audiobook library.
- Optional Readarr for book metadata/library context.

The Docker deployment starts BookBuddARR's web UI and optional Torznab bridge. It does not install or configure Prowlarr, qBittorrent, SABnzbd/NZBGet, Readarr, or Audiobookshelf for you.

## Product Status

Current state:

- Docker-first local web UI.
- CSV upload, validation, planning, ingest, candidate search, review, approval/rejection, and approved export.
- First-run stack settings for Prowlarr, qBittorrent, optional SABnzbd/NZBGet, Audiobookshelf, optional Readarr, root mappings, download mode, and import mode.
- Redacted connection tests.
- One-action monitored workflow from CSV to search, approval policy, grab, download monitoring, import, and Audiobookshelf-path verification.
- Actual-stack validation through Prowlarr, qBittorrent, and the Audiobookshelf filesystem mount.
- Multipart/volume candidates are flagged before approval.

Not yet complete:

- SABnzbd/NZBGet handoff is settings-only/TODO; qBittorrent is the implemented download monitor.
- Audiobookshelf API verification is optional; filesystem-path verification is implemented.
- Multipart grouping is enforced by state: single numbered parts become `needs_parts`; grouped completion requires multiple part candidates/downloads.

## Current Features

- Reads BookBuddy CSV exports in UTF-8.
- Validates BookBuddy CSV schema with `bookbuddarr doctor`.
- Previews first-run and later-run registry impact with `bookbuddarr plan`.
- Deduplicates books by ISBN when available.
- Falls back to normalized `title + author + language` when ISBN is missing.
- Maintains a persistent registry CSV so later exports only produce new books.
- Preserves language intent:
  - `français` / French books become `fr`.
  - `anglais` / English books become `en`.
- Applies audiobook-first rules:
  - French scanned editions target French audiobook results and `/Data/Audiobooks/Francais`.
  - English scanned editions target English audiobook results and `/Data/Audiobooks/English`.
  - Unknown-language books require manual language review.
- Generates:
  - `new_books.csv`
  - `readarr_queue.csv`
  - `audiobook_search_queue.csv`
- `audiobook_matches.csv` after reviewed dry-run search.
- Can list, approve, reject, and export approved audiobook candidates without grabbing or downloading.
- Preserves existing candidate `decision_status` and `notes` across search reruns.
- Can export approved candidates as CSV or export-only Audiobookshelf JSON.
- Supports optional audiobook language root mapping through a local JSON file.
- Can diff two BookBuddy exports without touching the registry.
- optional summary JSON
- Can run a small Torznab-compatible AudioBookBay bridge for Prowlarr testing.
- Can run a local Arr-style web UI for CSV upload, settings, planning, ingest, candidate decisions, approved export, and review-only audiobook search.

## Docker Quickstart

From the repo root:

```powershell
Copy-Item .env.example .env
notepad .env
docker compose -f deploy/service/compose.yaml up -d --build
```

Open:

```text
http://127.0.0.1:8788
```

Setup sequence:

1. Configure required services in `.env` or the web UI: Prowlarr URL/API key, qBittorrent URL/credentials/category, Audiobookshelf library path/root folders, and `BOOKBUDDARR_MEDIA` if your host media root should be mounted as `/Data`.
2. Optionally configure SABnzbd, NZBGet, Readarr, and the local Torznab bridge.
3. Click `Test Stack` and confirm output is redacted.
4. Upload a BookBuddy/Askademy Books-style CSV export.
5. Click `Run Workflow`.
6. Review `Workflow Status` for `needs_review`, `needs_parts`, `grabbing`, `downloading`, `complete`, or `blocked`.

Default `BOOKBUDDARR_DOWNLOAD_MODE=approved_only` will not grab new unapproved candidates. Set `BOOKBUDDARR_DOWNLOAD_MODE=approved_or_eligible` only when you want high-scoring, language-matching, non-multipart candidates to be eligible for automatic handoff.

## Python Install

From the repo root:

```powershell
python -m pip install -e .
```

Or run without installing:

```powershell
python -m bookbuddarr.cli ingest "C:\path\to\BookBuddy export.csv"
```

## Usage

Start with a validation pass:

```powershell
bookbuddarr doctor "C:\path\to\BookBuddy export.csv"
```

Preview the registry impact without writing outputs or updating local state:

```powershell
bookbuddarr plan "C:\path\to\BookBuddy export.csv" `
  --registry data\book_registry.csv
```

When the plan looks correct, ingest the export:

```powershell
bookbuddarr ingest "C:\path\to\BookBuddy export.csv" `
  --registry data\book_registry.csv `
  --new-csv data\new_books.csv `
  --readarr-csv data\readarr_queue.csv `
  --audiobook-csv data\audiobook_search_queue.csv `
  --summary-json data\summary.json
```

The first run treats every unique book as new and writes the registry.

The next run with a later BookBuddy export uses the same registry and outputs only new books.

To override default audiobook root hints, provide a local JSON file:

```json
{
  "fr": "/Data/Audiobooks/Francais",
  "en": "/Data/Audiobooks/English",
  "unknown": "/Data/Audiobooks"
}
```

Then pass it during ingest:

```powershell
bookbuddarr ingest "C:\path\to\BookBuddy export.csv" `
  --audiobook-root-map data\audiobook_roots.json
```

Local `.env` files are optional and loaded for endpoint configuration. API keys and other secrets must stay in local env files and are not printed by `doctor`.

## Monitored Workflow

Run the full approval-gated workflow from CLI:

```powershell
bookbuddarr workflow "C:\path\to\BookBuddy export.csv" --dry-run
```

Remove `--dry-run` after stack settings and review policy are correct. The workflow writes:

- `data/audiobook_matches.csv` for candidate review and Prowlarr grab metadata.
- `data/workflow_status.csv` for operational state.
- `data/workflow_activity.jsonl` for redacted activity events.

States include `needs_review`, `needs_parts`, `grabbing`, `downloading`, `complete`, `complete_grouped`, and `blocked`.

## Audiobook Candidate Review

After `ingest` creates `audiobook_search_queue.csv`, run a dry-run candidate search:

```powershell
bookbuddarr audiobook-search `
  --queue-csv data\audiobook_search_queue.csv `
  --matches-csv data\audiobook_matches.csv
```

By default, the command uses `TORZNAB_URL` and `TORZNAB_API_KEY` from `.env`, or falls back to the local bridge URL `http://127.0.0.1:8765/api`.

`audiobook_matches.csv` is a local review file. It includes:

- `record_id`
- book title, author, and BookBuddy language code
- search query
- candidate title
- candidate language and normalized language code
- candidate detail URL
- score
- completeness status and notes
- decision status
- notes

French records do not silently accept English candidates. Language mismatches are marked as `language_mismatch`; unknown-language books are marked for manual language review. The command does not request Torznab grab links and does not send anything to qBittorrent.

Candidates that look like a single numbered part, volume, tome, disc, or CD of a larger audiobook are marked as `needs_completeness_review`. They cannot be approved by default; either reject them or explicitly confirm that all parts are handled together.

During the monitored workflow, single numbered parts are surfaced as `needs_parts` and are not marked complete. If multiple sibling part candidates are present for the same BookBuddy record, the workflow can carry the grouped state forward as `complete_grouped` after download/import verification.

Review candidates explicitly:

```powershell
bookbuddarr candidates list --matches-csv data\audiobook_matches.csv
bookbuddarr candidates approve "isbn:9780000000000" "https://example.test/detail" `
  --matches-csv data\audiobook_matches.csv `
  --notes "Verified authorized source"
bookbuddarr candidates reject "isbn:9780000000000" "https://example.test/detail" `
  --matches-csv data\audiobook_matches.csv `
  --notes "Wrong language"
```

Export only approved candidates:

```powershell
bookbuddarr candidates export-approved `
  --matches-csv data\audiobook_matches.csv `
  --output data\approved_audiobook_candidates.csv
```

For Audiobookshelf planning, use the export-only JSON format. This writes a local file and does not call the Audiobookshelf API:

```powershell
bookbuddarr candidates export-approved `
  --matches-csv data\audiobook_matches.csv `
  --output data\audiobookshelf_wanted_export.json `
  --format audiobookshelf-json
```

## Export Diff

Compare two BookBuddy exports without reading or writing the registry:

```powershell
bookbuddarr diff-exports "C:\path\to\old.csv" "C:\path\to\new.csv"
```

## Local Web UI

Run the local UI:

```powershell
bookbuddarr web --bind 127.0.0.1 --port 8788
```

Then open:

```text
http://127.0.0.1:8788
```

The UI provides:

- BookBuddy CSV upload into ignored local `data/uploads/`.
- Settings for registry/output paths, Prowlarr, qBittorrent, optional SABnzbd/NZBGet, Audiobookshelf, optional Readarr, root folders, categories, and download/import modes.
- `Doctor`, `Plan`, `Ingest`, and review-only `Audiobook Search` actions.
- `Test Stack` and `Run Workflow` actions with redacted output.
- Candidate review table backed by `data/audiobook_matches.csv`.
- Workflow status table backed by `data/workflow_status.csv`.
- Approve/reject buttons that update the same CSV review state used by the CLI.
- Approved candidate export, candidate filtering, settings persistence, and an activity log.

The interface is an original Arr-style local control surface. It does not copy Sonarr/Radarr/Readarr source code or assets. Local settings are stored under ignored `data/`; API keys and passwords are masked in the browser response.

## Service Deployment

Repeatable Docker deployment files live under `deploy/service/`:

- `compose.yaml` for the `bookbuddarr-web` and `bookbuddarr-torznab` containers.
- `bookbuddarr-torznab.env.example` for Service-style secret-free env setup.
- `prowlarr_generic_torznab.py` to dry-run or apply the Prowlarr Generic Torznab indexer.
- `health_checks.py` for bridge, Prowlarr, and Readarr visibility checks.

On the current Service VM, the deployed web UI is:

```text
http://192.168.1.48:8788
```

Port `8788` is the web UI. Port `8765` is the Torznab bridge API and is expected to return `401` without an API key.

Start with the deployment guide:

```powershell
Get-Content deploy\service\README.md
```

## Stack Integration

### Audiobooks First

The primary workflow is audiobook discovery. Ebooks remain a review queue for later.

`audiobook_search_queue.csv` includes:

- `wanted_language`
- `language_policy`
- primary and alternate search queries
- Audiobookshelf/qBittorrent root hint
- manual review flag

### Readarr

`readarr_queue.csv` is a review/import queue. It includes title, author, ISBN, language code, and suggested Readarr metadata/root-folder hints.

Default root hints are:

- French: `/Data/Ebooks/Francais`
- English: `/Data/Ebooks/English`
- Unknown language: `/Data/Ebooks`

Direct Readarr API import is intentionally not enabled in v0.1 because book matching can be ambiguous. The safe workflow is:

1. Review the queue.
2. Confirm language and edition.
3. Add/search in Readarr.

In live testing, Readarr lookup could resolve a French ISBN to English/original metadata. BookBuddARR therefore preserves the BookBuddy language intent in the queue instead of trusting lookup metadata blindly.

### Audiobook Discovery

`audiobook_search_queue.csv` contains language-aware audiobook queries and review URLs.

These are review targets, not automated grabs. Only use them for content you have the right to access or redistribute.

AudioBookBay Automated is not a Prowlarr-style indexer. It is a separate search/download helper. BookBuddARR currently generates review queues for it instead of pretending it can be routed through Readarr like a normal Torznab/Newznab indexer.

### AudioBookBay Torznab Bridge

BookBuddARR can expose AudioBookBay search through a small Torznab-compatible bridge:

```powershell
bookbuddarr torznab-serve --bind 127.0.0.1 --port 8765 --page-limit 2 --api-key "local-dev-key" --default-query "audiobook"
```

Then add a Generic Torznab indexer in Prowlarr:

- URL: `http://<host>:8765/api`
- API Key: the value passed with `--api-key`
- Categories: audiobook/books as desired

The bridge searches and returns Torznab XML. It does not send anything to qBittorrent. Grab links are proxied through `t=get` and redirect to a magnet only when the downstream app explicitly requests a result.

Prowlarr validates Generic Torznab indexers by running a query without a user search term. `--default-query` controls the fallback query for that validation/RSS path.

Keep this disabled or LAN-only until the matching and language rules are validated.

Docker:

```powershell
docker build -t bookbuddarr:local .
docker run --rm -p 8765:8765 bookbuddarr:local bookbuddarr torznab-serve --bind 0.0.0.0 --port 8765 --api-key "local-dev-key" --default-query "audiobook"
```

## Why Not Autobrr First?

Autobrr is useful for reacting quickly to tracker announcements and freeleech opportunities. BookBuddARR's first job is different: convert a personal catalog into deterministic, incremental search queues. For existing books, Readarr and manual/reviewed audiobook searches are usually the right first integration points.

## Local Data

The `data/` folder is ignored by Git except for `.gitkeep`. Keep BookBuddy exports, registries, generated queues, and local secrets out of the public repo.

## QA

The public CI workflow runs tests, CLI help checks, and Service script compilation. Local validation:

```powershell
python -m pytest tests
python -m bookbuddarr.cli --help
python -m bookbuddarr.cli ingest --help
python -m bookbuddarr.cli audiobook-search --help
python -m bookbuddarr.cli candidates --help
python -m bookbuddarr.cli diff-exports --help
python -m bookbuddarr.cli torznab-serve --help
python -m bookbuddarr.cli web --help
python -m py_compile deploy\service\prowlarr_generic_torznab.py deploy\service\health_checks.py
```
