# BookBuddARR Product Finalization Handoff Prompt

You are Codex working in `C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR`.

Goal: advance BookBuddARR from a v1 integrated POC to a product-grade audiobook-first workflow.

## Mandatory Context

Read these files first:

1. `README.md`
2. `docs/product-status.md`
3. `docs/product-backlog.md`
4. `docs/architecture.md`
5. `docs/decisions/ADR-0001-csv-registry-first.md`
6. `docs/decisions/ADR-0002-review-queues-before-automation.md`
7. `docs/decisions/ADR-0003-audiobook-first-torznab-bridge.md`
8. `TODO.md`

Then inspect:

- `bookbuddarr/cli.py`
- `bookbuddarr/bookbuddy.py`
- `bookbuddarr/outputs.py`
- `bookbuddarr/rules.py`
- `bookbuddarr/torznab.py`
- `tests/test_pipeline.py`

## Current Live Facts

- Public repo: `https://github.com/Nassau-1/BookBuddARR`
- Current stage: v1 integrated POC.
- Primary product direction: audiobook-first.
- Ebooks are WIP and secondary.
- BookBuddy language intent is authoritative.
- Local generated exports/registries under `data/` must stay ignored and uncommitted.
- Service stack has a deployed `bookbuddarr-torznab` container on port `8765`.
- Prowlarr has `AudioBookBay Bridge`.
- Readarr sees `AudioBookBay Bridge (Prowlarr)`.
- Broad AudioBookBay searches are noisy; review-first is required.

## Safety Rules

- Do not print API keys, tracker keys, qBittorrent credentials, BookBuddy personal export contents, or generated personal registry contents.
- Do not auto-grab or auto-download audiobook results.
- Do not remove review gates.
- Keep the public repo free of personal collection data.
- Keep tests using synthetic fixture data only.
- Prefer dry-run commands before any stateful action.

## Suggested Subagents

Spawn focused subagents if your environment supports it:

### 1. Product Architect

Task:

- Convert `docs/product-backlog.md` into a coherent milestone plan.
- Define the smallest true product milestone after the POC.
- Decide whether persistent review state should be CSV or SQLite.
- Output: `docs/roadmap.md` and any ADR needed.

Acceptance:

- Roadmap separates P0/P1/P2 clearly.
- Includes user-facing workflow.
- Does not add auto-grab before candidate review exists.

### 2. CLI Engineer

Task:

- Implement `bookbuddarr doctor`.
- Implement `bookbuddarr plan`.
- Improve missing-column diagnostics.
- Add `.env` loading for optional local endpoints without new mandatory dependencies unless justified.

Acceptance:

- Tests cover good CSV, missing required columns, first-run/new-run counts.
- No secrets printed.
- Commands work on Windows PowerShell.

### 3. Audiobook Matching Engineer

Task:

- Implement `bookbuddarr audiobook-search` in dry-run/review mode.
- Query the Torznab bridge or Prowlarr.
- Persist candidate matches locally.
- Add language-aware filtering and ranking.

Acceptance:

- No grabs.
- Candidate CSV/SQLite includes candidate URL, title, language, score, decision status.
- French records do not silently accept English candidates.
- Tests use mocked Torznab XML.

### 4. Service Deployment Engineer

Task:

- Add `deploy/service/` with compose and install/update docs.
- Add a Prowlarr Generic Torznab setup/update script.
- Add health-check commands.

Acceptance:

- Deployment is repeatable on Service.
- API keys come from env files.
- Prowlarr setup script redacts secrets in output.

### 5. QA/Docs Engineer

Task:

- Expand README into a clean user guide.
- Add troubleshooting for noisy ABB results, language mismatch, Readarr metadata mismatch, and Prowlarr validation.
- Add CI or at least documented local QA commands.

Acceptance:

- `python -m pytest tests` passes.
- Docs clearly state POC/product limits.
- Public wording avoids implying illegal download automation.

## First Implementation Slice

Recommended first slice:

1. Add `bookbuddarr doctor`.
2. Add `bookbuddarr plan`.
3. Add synthetic fixtures for BookBuddy CSVs.
4. Add `docs/roadmap.md`.
5. Keep all network/search work dry-run.

This creates a product-safe foundation before expanding toward candidate search and approval flows.

## Validation Commands

Run:

```powershell
python -m pytest tests
python -m bookbuddarr.cli --help
python -m bookbuddarr.cli ingest --help
python -m bookbuddarr.cli torznab-serve --help
```

If touching Service deployment, verify live stack without printing secrets:

```powershell
ssh service "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'bookbuddarr|prowlarr|readarr'"
ssh service "curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8765/api?t=caps'"
```

The second command should return `401` if API key protection is active.

## Definition Of Done

- Code implemented.
- Tests added/updated and passing.
- Public docs updated.
- No local generated data committed.
- Clear final summary with what is product-ready, what remains review-only, and what is blocked.
