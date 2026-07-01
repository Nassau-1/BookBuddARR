# ADR-0001: CSV Registry First

Date: 2026-07-01

## Status

Accepted

## Context

BookBuddy exports are user-controlled CSV files. The workflow needs to process later exports incrementally without re-triggering searches for the whole library.

## Decision

Use a local CSV registry as the v0 persistence layer.

The registry stores stable `record_id` values plus the main bibliographic fields required for review.

## Consequences

- Easy to inspect and edit manually.
- Works on Windows without a database service.
- Safe to keep local and out of Git.
- Later versions can add SQLite without changing the public ingestion model.
