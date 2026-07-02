# Goal Prompt: Fix Real CSV Workflow

Finish the real-user BookBuddARR workflow so the Docker UI can take the Askademy/BookBuddy export, search useful audiobook candidates, and move actionable rows toward approved grab/import instead of ending in an all-blocked dead end.

Workspace:

`C:\Users\EnzoTERRIER\Codex\projects\BookBuddARR`

Read first:

1. `README.md`
2. `TODO.md`
3. `docs/product-status.md`
4. `docs/product-backlog.md`
5. `docs/roadmap.md`
6. `docs/architecture.md`
7. `bookbuddarr/web.py`
8. `bookbuddarr/workflow.py`
9. `bookbuddarr/stack.py`
10. `bookbuddarr/audiobook_search.py`
11. `tests/test_pipeline.py`

Current evidence from 2026-07-02 real UI validation:

- Service URL: `http://192.168.1.48:8788/`
- Real source CSV: `C:\Users\EnzoTERRIER\Downloads\BookBuddy 2026-07-01 224447.csv`
- Upload through `/api/upload` succeeds and stores the file at `/data/uploads/BookBuddy 2026-07-01 224447.csv`.
- Plan succeeds:
  - `input_rows`: `143`
  - `unique_rows`: `143`
  - `new_records`: `143`
  - language split: `122` French, `20` English, `1` unknown
- Stack test succeeds:
  - Prowlarr connected
  - qBittorrent connected
  - Audiobookshelf verified `/Data/Audiobooks`
  - SABnzbd/NZBGet are optional and not configured
- Docker persistence bug was fixed: web defaults now use `BOOKBUDDARR_DATA_DIR`, and Service sets it to `/data`.
- UI bug was fixed: first viewport now shows CSV state, stack state, workflow state, and the workflow summary. It correctly shows `143 blocked` after the failed run.
- Real `Run Workflow` still fails the target product flow:
  - `/api/workflow` returns `ok: false`
  - states: `{"blocked": 143}`
  - `/data/workflow_status.csv` has 143 rows
  - every row has `details=no_candidates_found`
  - `/data/audiobook_matches.csv` has 0 rows

Important diagnosis:

- Prowlarr is not globally broken. Manual test from the container returned results for `Dune Frank Herbert`.
- The generated queries for the real CSV returned no releases, including simplified checks for examples such as:
  - `Ainsi parlait Zarathoustra`
  - `Antifragile`
  - `Bonjour tristesse`
  - `Born for War`
- The immediate blocker is therefore the real candidate discovery/search strategy for this catalog and current indexer set, not CSV parsing, Docker networking, or stack credentials.

Target user flow:

1. User installs with Docker Compose.
2. User opens the web UI.
3. User configures Prowlarr, qBittorrent, Audiobookshelf, and optional services.
4. User drops the Askademy/BookBuddy CSV.
5. User clicks one workflow action.
6. BookBuddARR searches useful audiobook candidates for each book, preserves language intent, and creates actionable review/eligible rows.
7. Approved or eligible rows are grabbed, monitored, imported, and verified.
8. Multipart releases are grouped before completion.
9. Rows with no viable release are clearly reported, but the full catalog should not collapse to 143 identical dead-end blocked rows when alternative query strategies or review search states could be useful.

Required work:

1. Reproduce the real workflow failure against Service or an equivalent local fixture.
2. Improve candidate discovery:
   - Try progressive query fallback, for example full query, title + primary author, title only, normalized ASCII title, and language-free variants.
   - Consider indexer/category behavior in Prowlarr. Do not hard-code only a strategy that works for one tracker.
   - Preserve BookBuddy language intent in scoring/review, but do not poison search with language words when they reduce recall.
   - Record which query variant produced each candidate.
3. Improve workflow states:
   - Distinguish `no_candidates_found` from `needs_review`.
   - If search was exhausted, include the attempted query variants or a compact count in `details`.
   - Keep `blocked` for true terminal states, but consider a more actionable state for “no release found yet”.
4. Improve UI:
   - First viewport must make the result understandable after a run.
   - Workflow status should summarize counts and top reasons.
   - Candidate Review should make empty states actionable, not just blank.
5. Preserve safety:
   - Do not print or commit API keys, tracker keys, qBittorrent credentials, env files, personal CSV contents, generated registries, or generated matches.
   - Keep default download mode safe. Do not mass-grab ambiguous releases.
6. Validate:
   - `python -m pytest tests`
   - `python -m py_compile bookbuddarr\web.py bookbuddarr\workflow.py bookbuddarr\stack.py`
   - Service web UI returns HTTP 200.
   - Upload real CSV.
   - Plan real CSV.
   - Test Stack from UI or endpoint.
   - Run Workflow on the real CSV.
   - Confirm the final state is no longer a useless `143 blocked / no_candidates_found` dead end, or document exactly which external indexer/source limitation remains.

Definition of done:

- The real CSV user flow either produces actionable candidate/review rows and downstream progress, or it clearly proves the external source/indexer limitation with useful per-row status and next actions.
- The Docker UI no longer looks like a static technical form as the primary experience.
- Docker outputs are persisted under `/data`.
- Tests pass.
- No secrets or personal data are committed.
