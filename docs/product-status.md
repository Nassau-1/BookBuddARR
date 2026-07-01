# Product Status

Date: 2026-07-01

## Current Stage

BookBuddARR is a **v1 integrated POC**, not yet a finished product.

It has real working pieces:

- BookBuddy CSV ingestion.
- Stable registry to avoid reprocessing old exports.
- ISBN-first deduplication.
- Language-aware audiobook routing rules.
- Generated audiobook review queue.
- Optional AudioBookBay Torznab bridge.
- Deployed Service-stack bridge proof.
- Prowlarr `AudioBookBay Bridge` indexer proof.
- Readarr visibility proof.

But it is not yet product-complete:

- No one-command Service deployment.
- No UI.
- No automated safe matching/import flow.
- No persisted match-review state.
- No end-to-end "BookBuddy export -> approved audiobook request -> qBittorrent -> Audiobookshelf" flow.
- No production observability around bridge failures or noisy results.

## Proven Live State

Local repo:

- Path: `C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR`
- GitHub: `https://github.com/Nassau-1/BookBuddARR`
- Latest known pushed commit: `6ba3ddb`
- Tests: `python -m pytest tests` passes with 7 tests.

Service VM:

- `bookbuddarr-torznab` runs on port `8765`.
- API key is stored on Service at `/srv/media-stack/compose/bookbuddarr-torznab.env`.
- Prowlarr indexer `AudioBookBay Bridge` exists and passes test.
- Readarr sees `AudioBookBay Bridge (Prowlarr)`.

BookBuddy export proof:

- Input rows: `143`
- Unique rows: `143`
- Duplicates in export: `0`
- Language split: `122` French, `20` English, `1` unknown

## Product Definition

The intended final product is:

> A self-hosted bridge that turns repeated BookBuddy exports into a reviewed, language-aware audiobook request pipeline for Arr-style stacks, with optional Torznab search routing through Prowlarr and safe handoff to qBittorrent/Audiobookshelf.

## Non-Goals For Now

- Fully automatic grabbing from AudioBookBay without review.
- Circumventing tracker or site rules.
- Publishing or redistributing protected works.
- Treating Readarr metadata as authoritative when it contradicts BookBuddy language intent.
- Replacing Prowlarr; BookBuddARR should complement it.
