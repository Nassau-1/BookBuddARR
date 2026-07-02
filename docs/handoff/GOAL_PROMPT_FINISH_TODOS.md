# BookBuddARR Finish-TODO Goal Prompt

Use this in a fresh Codex session:

For the full Service/live-validation phase, prefer `docs/handoff/GOAL_PROMPT_LIVE_COMPLETION.md`.

```text
/goal Finish the remaining BookBuddARR product TODOs in C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR.

Mandatory context:
Read README.md, TODO.md, docs/product-status.md, docs/product-backlog.md, docs/roadmap.md, docs/architecture.md, docs/decisions/ADR-0001-csv-registry-first.md, docs/decisions/ADR-0002-review-queues-before-automation.md, docs/decisions/ADR-0003-audiobook-first-torznab-bridge.md, docs/decisions/ADR-0004-csv-review-state-before-sqlite.md, and docs/handoff/PRODUCT_FINALIZATION_PROMPT.md. Then inspect bookbuddarr/cli.py, bookbuddarr/audiobook_search.py, bookbuddarr/web.py, deploy/service/README.md, deploy/service/prowlarr_generic_torznab.py, deploy/service/health_checks.py, and tests/test_pipeline.py.

Current state:
BookBuddARR has doctor, plan, ingest, audiobook-search, candidates list/approve/reject/export-approved, diff-exports, torznab-serve, and web commands. The local Arr-style UI has been accepted for now. Candidate discovery is dry-run/review-only and writes local CSV review state. Candidate decisions and approved export use the same CSV state from CLI and web. Service deployment packaging exists under deploy/service. Public repo: https://github.com/Nassau-1/BookBuddARR. data/ must remain ignored and uncommitted except data/.gitkeep.

Remaining TODOs to finish:
1. Sync and run the final implementation on Service.
2. Validate Service web UI, Torznab bridge protection, Prowlarr visibility, and Readarr visibility without printing secrets.
3. Complete live validation with at least 3 lawful/authorized audiobooks found through the BookBuddARR review workflow, manually approved, downloaded/imported, visible in the target library/location, and confirmed in the correct BookBuddy intended language.
4. If lawful/authorized titles are unavailable, document the exact blocker and do not substitute unauthorized downloads.

Safety rules:
Do not print API keys, tracker keys, qBittorrent credentials, BookBuddy personal export contents, or generated personal registry contents. Do not auto-grab or auto-download audiobook results. Do not add a qBittorrent handoff unless it is export-only and explicitly review-gated. Do not remove review gates. Keep public tests on synthetic fixtures only. Keep local generated data under ignored data/ paths.

Implementation guidance:
Prefer CSV review state for now per ADR-0004. Preserve existing decision_status and notes on reruns. Add commands such as candidate approve/reject/list/export if they fit the existing CLI style. The web UI should call the same backend logic and should not create a separate persistence model. Approved exports should be plain local files with clear columns and no automatic downstream mutation. For language roots, default to current French/English/unknown behavior and allow config overrides without requiring new dependencies.

Acceptance:
python -m pytest tests passes. CLI help passes for all commands. README, TODO, product-status/backlog, roadmap, and architecture reflect the final state. No generated data or secrets are tracked. Final summary states what is product-ready, what remains review-only, live validation evidence, and any blocked live-Service verification.

Validation commands:
python -m pytest tests
python -m bookbuddarr.cli --help
python -m bookbuddarr.cli ingest --help
python -m bookbuddarr.cli audiobook-search --help
python -m bookbuddarr.cli candidates --help
python -m bookbuddarr.cli diff-exports --help
python -m bookbuddarr.cli torznab-serve --help
python -m bookbuddarr.cli web --help

If touching deploy/service, run only secret-safe checks unless explicitly asked to mutate Service:
ssh service "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'bookbuddarr|prowlarr|readarr'"
ssh service "curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8765/api?t=caps'"
Expected unauthenticated caps result: 401.
```
