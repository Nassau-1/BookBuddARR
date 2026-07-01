# ADR-0003: Audiobook-First Rules and Optional Torznab Bridge

Date: 2026-07-01

## Status

Accepted

## Context

The immediate user workflow is not ebook acquisition. It is turning a physical BookBuddy catalog into audiobook discovery, with language fidelity from the scanned edition.

AudioBookBay Automated exists in the local stack, but it is a search/download helper, not a Prowlarr-compatible Torznab indexer.

## Decision

BookBuddARR keeps ebooks as a secondary review queue and prioritizes audiobook rules.

It also provides an optional Torznab bridge that can expose AudioBookBay search to Prowlarr as Generic Torznab.

## Consequences

- French scanned books generate French audiobook search intent.
- English scanned books generate English audiobook search intent.
- Unknown-language books require manual review.
- The Torznab bridge does not download or add torrents.
- Prowlarr integration can be tested without modifying AudioBookBay Automated.
