# BookBuddARR Service Deployment

This folder contains the repeatable Docker Compose deployment for BookBuddARR web UI, optional Torznab bridge, and helper scripts used to wire the bridge into Prowlarr.

The deployment is approval-gated. BookBuddARR can search through Prowlarr and hand approved or explicitly eligible releases to the configured stack, but ambiguous language matches and single-part multipart candidates remain blocked for review.

## General Docker Install

From the repository root:

```bash
cp .env.example .env
nano .env
docker compose -f deploy/service/compose.yaml up -d --build
```

Required values:

- `BOOKBUDDARR_TORZNAB_API_KEY`
- `PROWLARR_URL`
- `PROWLARR_API_KEY`
- `QBITTORRENT_URL`
- `QBITTORRENT_USERNAME`
- `QBITTORRENT_PASSWORD`
- `QBITTORRENT_CATEGORY`
- `AUDIOBOOKSHELF_LIBRARY_PATH`
- `AUDIOBOOK_ROOT_FR`
- `AUDIOBOOK_ROOT_EN`
- `AUDIOBOOK_ROOT_UNKNOWN`

Optional values:

- `SABNZBD_URL` / `SABNZBD_API_KEY`
- `NZBGET_URL` / `NZBGET_USERNAME` / `NZBGET_PASSWORD`
- `READARR_URL` / `READARR_API_KEY`
- `AUDIOBOOKSHELF_URL` / `AUDIOBOOKSHELF_API_KEY`

Open:

```text
http://127.0.0.1:8788
```

## Expected Service Anchors

Current known Service stack anchors:

- Compose root: `/srv/media-stack/compose`
- Source checkout: `/srv/media-stack/compose/bookbuddarr-src`
- Env file: `/srv/media-stack/compose/bookbuddarr-torznab.env`
- Docker network: `mediaNet`
- Bridge container: `bookbuddarr-torznab`
- Bridge port: `8765`
- Web UI container: `bookbuddarr-web`
- Web UI port: `8788`
- Web UI data path: `/srv/media-stack/compose/bookbuddarr-data`

## Install Or Update

From this workstation:

```powershell
ssh service "mkdir -p /srv/media-stack/compose/bookbuddarr-src"
git archive --format=tar HEAD | ssh service "tar -x -C /srv/media-stack/compose/bookbuddarr-src"
```

On Service, create the env file from the template:

```bash
cd /srv/media-stack/compose/bookbuddarr-src
cp deploy/service/bookbuddarr-torznab.env.example /srv/media-stack/compose/bookbuddarr-torznab.env
chmod 600 /srv/media-stack/compose/bookbuddarr-torznab.env
nano /srv/media-stack/compose/bookbuddarr-torznab.env
```

Set real values for at least:

- `BOOKBUDDARR_TORZNAB_API_KEY`
- `BOOKBUDDARR_SRC`
- `BOOKBUDDARR_ENV`
- `BOOKBUDDARR_NETWORK=mediaNet` and `BOOKBUDDARR_NETWORK_EXTERNAL=true` when sharing an existing Service Docker network with Prowlarr/qBittorrent/Audiobookshelf.
- `PROWLARR_URL`
- `PROWLARR_API_KEY`
- `QBITTORRENT_URL`
- `QBITTORRENT_USERNAME`
- `QBITTORRENT_PASSWORD`
- `AUDIOBOOKSHELF_LIBRARY_PATH`
- language root mappings

Start or update the bridge:

```bash
cd /srv/media-stack/compose/bookbuddarr-src
docker compose --env-file /srv/media-stack/compose/bookbuddarr-torznab.env \
  -f deploy/service/compose.yaml up -d --build
```

The same compose file starts both:

- `bookbuddarr-torznab` on `8765`
- `bookbuddarr-web` on `8788`

Open the Service web UI from the LAN or tunnel:

```text
http://192.168.1.48:8788
```

The web UI stores local uploads and settings under `/srv/media-stack/compose/bookbuddarr-data`.

## Monitored Workflow

Use the web UI `Run Workflow` action or CLI:

```bash
bookbuddarr workflow /data/uploads/bookbuddy.csv --dry-run
```

Remove `--dry-run` only after connection tests pass and review policy is correct. Default `BOOKBUDDARR_DOWNLOAD_MODE=approved_only` means the workflow searches and writes status but only grabs already-approved rows. `approved_or_eligible` allows high-scoring, language-matching, non-multipart candidates to proceed.

Workflow status is written to `data/workflow_status.csv`. Single numbered parts are `needs_parts` and are not complete until sibling parts are present and grouped.

## Prowlarr Generic Torznab Setup

Dry-run first:

```bash
cd /srv/media-stack/compose/bookbuddarr-src
python deploy/service/prowlarr_generic_torznab.py \
  --env-file /srv/media-stack/compose/bookbuddarr-torznab.env
```

Apply after reviewing the redacted payload preview:

```bash
python deploy/service/prowlarr_generic_torznab.py \
  --env-file /srv/media-stack/compose/bookbuddarr-torznab.env \
  --apply
```

The helper creates or updates the `AudioBookBay Bridge` Generic Torznab indexer. It uses Prowlarr's live Generic Torznab schema and redacts API keys in console output.

## Health Checks

Container status:

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'bookbuddarr|prowlarr|readarr'
```

Unauthenticated bridge caps should be protected:

```bash
curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8765/api?t=caps'
```

Expected result:

```text
401
```

Authenticated bridge caps should work:

```bash
. /srv/media-stack/compose/bookbuddarr-torznab.env
curl -s -o /dev/null -w '%{http_code}\n' \
  "http://127.0.0.1:8765/api?t=caps&apikey=${BOOKBUDDARR_TORZNAB_API_KEY}"
```

Expected result:

```text
200
```

Run the combined health script:

```bash
cd /srv/media-stack/compose/bookbuddarr-src
python deploy/service/health_checks.py \
  --env-file /srv/media-stack/compose/bookbuddarr-torznab.env
```

The health script checks:

- unauthenticated bridge caps returns `401`
- authenticated bridge caps returns `200` and XML caps
- Prowlarr sees the configured indexer when `PROWLARR_API_KEY` is provided
- Readarr sees the Prowlarr-backed indexer when `READARR_API_KEY` is provided

## Troubleshooting

### Prowlarr Validation Fails

- Confirm the bridge container is running.
- Confirm `BOOKBUDDARR_TORZNAB_API_KEY` in Prowlarr matches the Service env file.
- Confirm Prowlarr can resolve `bookbuddarr-torznab` on `mediaNet`.
- Confirm the Generic Torznab URL/API path resolves to `/api`.

### Bridge Returns 401 In Prowlarr

The API key is missing or mismatched. Re-check the env file and rerun the Prowlarr setup helper with `--apply`.

### Broad AudioBookBay Results Are Noisy

This is expected. Keep BookBuddARR queries title + author + language-aware, then review candidates in `audiobook_matches.csv` or the local UI. Do not enable automatic grabs from broad results.

### Readarr Metadata Does Not Match BookBuddy Language

BookBuddy language intent remains authoritative. Do not accept English metadata for French BookBuddy records without manual review.
