# ADR-0002: Review Queues Before Automation

Date: 2026-07-01

## Status

Accepted

## Context

Book and audiobook matching is ambiguous. A scanned physical edition can map to multiple ebooks, audiobooks, languages, narrators, abridged editions, or translations.

## Decision

BookBuddARR v0 produces review queues instead of directly triggering downloads or grabs.

## Consequences

- Reduces false positives.
- Preserves language intent from BookBuddy.
- Keeps the public project focused on catalog bridging rather than media acquisition.
- Future API integrations should remain opt-in and dry-run first.
