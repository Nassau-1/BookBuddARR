# Architecture

BookBuddARR is a local CLI pipeline.

```mermaid
flowchart LR
  A["BookBuddy CSV export"] --> B["Parser"]
  B --> C["Normalizer"]
  C --> D["Deduper"]
  D --> E["Persistent registry CSV"]
  D --> F["New books CSV"]
  D --> G["Readarr review queue"]
  D --> H["Audiobook search queue"]
```

## Components

- `bookbuddarr.bookbuddy`: reads BookBuddy CSV rows and converts them into normalized records.
- `bookbuddarr.normalize`: text, ISBN, and language normalization.
- `bookbuddarr.registry`: persistent processed-record registry.
- `bookbuddarr.outputs`: generated CSV queues.
- `bookbuddarr.cli`: command-line interface.

## Identity Model

Record identity is ISBN-first:

1. If ISBN is present, use `isbn:<normalized ISBN>`.
2. Otherwise, use a stable hash of normalized title, author, and language.

This avoids reprocessing the same scanned edition on later BookBuddy exports while still supporting books without ISBN.

## Integration Boundary

BookBuddARR intentionally does not download or grab releases. It produces review queues for downstream tools such as Readarr and audiobook discovery/search services.

This keeps the first version deterministic, auditable, and safe for public release.
