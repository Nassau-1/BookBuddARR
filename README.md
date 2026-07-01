# BookBuddARR

BookBuddARR bridges [BookBuddy](https://www.kimicoapps.com/bookbuddy/) CSV exports into self-hosted book and audiobook workflows.

It is designed for a simple loop:

1. Export your library from BookBuddy as CSV.
2. Run `bookbuddarr ingest`.
3. Keep a persistent local registry of books already processed.
4. Produce queues for only the newly scanned books.
5. Review/import those queues into Readarr and audiobook discovery tools.

BookBuddARR does not download media by itself. It creates structured queues and review links so your existing stack can handle lawful acquisition, matching, and library management.

## Current Features

- Reads BookBuddy CSV exports in UTF-8.
- Deduplicates books by ISBN when available.
- Falls back to normalized `title + author + language` when ISBN is missing.
- Maintains a persistent registry CSV so later exports only produce new books.
- Preserves language intent:
  - `français` / French books become `fr`.
  - `anglais` / English books become `en`.
- Generates:
  - `new_books.csv`
  - `readarr_queue.csv`
  - `audiobook_search_queue.csv`
  - optional summary JSON

## Install

From the repo root:

```powershell
python -m pip install -e .
```

Or run without installing:

```powershell
python -m bookbuddarr.cli ingest "C:\path\to\BookBuddy export.csv"
```

## Usage

```powershell
bookbuddarr ingest "C:\Users\EnzoTERRIER\Downloads\BookBuddy 2026-07-01 224447.csv" `
  --registry data\book_registry.csv `
  --new-csv data\new_books.csv `
  --readarr-csv data\readarr_queue.csv `
  --audiobook-csv data\audiobook_search_queue.csv `
  --summary-json data\summary.json
```

The first run treats every unique book as new and writes the registry.

The next run with a later BookBuddy export uses the same registry and outputs only new books.

## Stack Integration

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

## Why Not Autobrr First?

Autobrr is useful for reacting quickly to tracker announcements and freeleech opportunities. BookBuddARR's first job is different: convert a personal catalog into deterministic, incremental search queues. For existing books, Readarr and manual/reviewed audiobook searches are usually the right first integration points.

## Local Data

The `data/` folder is ignored by Git except for `.gitkeep`. Keep BookBuddy exports, registries, generated queues, and local secrets out of the public repo.
