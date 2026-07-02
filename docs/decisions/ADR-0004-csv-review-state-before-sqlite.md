# ADR-0004: CSV Review State Before SQLite

Date: 2026-07-01

## Status

Accepted

## Context

The next product milestone needs persistent audiobook candidate review state. The state must be inspectable, easy to back up, safe for Windows-first local workflows, and compatible with the existing CSV registry model.

SQLite would provide stronger query semantics and safer multi-step updates, but the immediate workflow is still single-user, local, and review-first.

## Decision

Use a local CSV file for the first persistent audiobook candidate review state.

The review CSV should include:

- `record_id`
- `search_query`
- `candidate_title`
- `candidate_language`
- `candidate_url`
- `score`
- `decision_status`
- `notes`

SQLite remains the expected later persistence option if review history, concurrent edits, richer filtering, or UI-backed workflows outgrow CSV.

## Consequences

- Keeps the next milestone consistent with the existing CSV registry.
- Makes candidate state easy to inspect and repair manually.
- Avoids a database migration before the candidate schema is proven.
- Requires careful CSV deduplication and atomic write discipline.
- Does not permit auto-grab; candidates remain pending until explicitly reviewed.
