# Security Policy

## Supported Versions

BookBuddARR is currently pre-1.0. Security fixes are applied to the latest main branch.

## Sensitive Data

Do not commit:

- BookBuddy exports from a personal library
- Readarr API keys
- Audiobook site credentials
- qBittorrent credentials
- Generated registries or queues that reveal a private collection

The default `.gitignore` excludes `data/` contents and `.env*` files.

## Reporting Issues

Open a private issue or contact the maintainer directly if a vulnerability could expose library data, credentials, or local service URLs.
