<h1 align="center">WebMonitor-Agent</h1>

<p align="center">
  <strong>Describe what to watch. Get notified when it changes.</strong>
</p>

<p align="center">
  Follow prices, restocks, announcements, and deadlines.<br>
  Create a monitor through conversation, review a real preview, and receive email updates.
</p>

<p align="center">
  <a href="#what-you-can-follow">Use cases</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#deploy-the-published-image">Get started</a> ·
  <a href="#operate-the-stack">Operations</a> ·
  <a href="#data-lifetime-upgrades-and-rollbacks">Data and upgrades</a> ·
  <a href="https://github.com/webmonitor/WebMonitor-Agent/blob/main/.env.example">Configuration reference</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

WebMonitor-Agent is a self-hosted web monitoring assistant. Paste a link and describe what matters, how often to check, and when to notify you. The assistant analyzes the live page and prepares a monitor. You see the actual collection result before enabling it, without writing selectors yourself. Scheduled checks compare later content and send email only when your rules match.

## What you can follow

| Keep an eye on | Describe what you need |
| --- | --- |
| Price changes | “Check this product every 10 minutes and email me when its price drops below ¥200.” |
| Restocks | “Watch this product's availability and notify me when it changes from out of stock to in stock.” |
| Announcements | “Check this announcement list every hour and email me when a new item appears.” |
| Deadline changes | “Track the registration deadline on this page and tell me if it changes.” |

## How it works

1. **Describe your goal.** Start a conversation with the page URL, what to watch, a check interval, and the conditions for a notification.
2. **Review a real preview.** The assistant opens the page and collects its content. Check the extracted values, coverage, notification rules, recipients, and email preview.
3. **Confirm and start.** Approve the monitor to begin scheduled checks. Review changes, pause or resume monitoring, and use the conversation to adjust what you need.

The first successful scheduled check saves the starting content for later comparisons and sends no change notification. Previews do not send email either. Later changes trigger alerts only when they meet your rules.

## From a change to the details

- **Choose when to hear about it.** Set rules for text, keywords, numeric changes, thresholds, and new or updated list items. Removed items can also be tracked when complete list coverage is confirmed.
- **See the evidence.** Compare previous and current content and open the page archive saved from that check. Browser-based collection also captures a screenshot.
- **Notify the right people.** Select from notification groups maintained by the administrator. One monitor can notify multiple email addresses.
- **Keep track of activity.** Manage conversations, monitors, and events in one workspace, with recent check results and email delivery status. The interface is available in English and Chinese.
- **Review changes before applying them.** Preview and confirm monitor edits. A failed check preserves the last successful content as the comparison baseline.

By default, monitoring supports public HTTP/HTTPS pages with check intervals from 1 minute to 24 hours. The preview explains what was actually collected and any coverage limitations. Content inside iframes or Shadow DOM is not currently extracted.

## Requirements

- Docker Engine with Docker Compose v2 on Linux, macOS, or Windows.
- An OpenAI Chat Completions-compatible model service for the conversation. Set its API key, base URL, and model name.
- An SMTP service if you want email alerts.
- The published application image is available for `linux/amd64` and `linux/arm64`.
- No Git checkout is required for the published-image deployment.

## Deploy the published image

WebMonitor-Agent publishes one application image to GitHub Container Registry:

```text
ghcr.io/webmonitor/webmonitor-agent
```

That single image contains the Python API and worker loops, the built Next.js frontend, and Chromium. Compose runs it as two services with different entrypoints: `api` and `web`. The public image is available on both `linux/amd64` and `linux/arm64`:

```sh
docker pull ghcr.io/webmonitor/webmonitor-agent:latest
```

> **A pull is not a deployment.** The command above only confirms that the public image can be downloaded anonymously. It does not create configuration, start PostgreSQL or evidence storage, run the worker, or serve the interface. A runnable deployment also needs `compose.yaml`, the nginx and seccomp files it mounts, the Dockerfiles for the locally built `s3` and `egress` helper images, and an `.env` file.

The normal installation creates an empty deployment directory and downloads only those runtime files. Do not clone the repository for this path.

### 1. Download the runtime files

```sh
mkdir -p webmonitor-agent/deploy/proxy webmonitor-agent/deploy/egress
cd webmonitor-agent

set -eu
BASE=https://raw.githubusercontent.com/webmonitor/WebMonitor-Agent/main

for path in \
  compose.yaml \
  .dockerignore \
  deploy/proxy/nginx.conf \
  deploy/browser-seccomp.json \
  deploy/minio.Dockerfile \
  deploy/egress.Dockerfile \
  deploy/egress/squid.conf \
  deploy/egress/unbound.conf \
  deploy/egress/entrypoint.sh \
  deploy/minio-artifacts.json
do
  if ! curl --fail --silent --show-error --location "$BASE/$path" --output "$path"; then
    printf 'download failed: %s\n' "$path" >&2
    exit 1
  fi
done
```

If any download fails, the loop exits with an error. Do not start Compose until every file is present.

The loop preserves the directory layout that `compose.yaml` expects:

```text
webmonitor-agent/
├── .dockerignore
├── .env
├── compose.yaml
└── deploy/
    ├── browser-seccomp.json
    ├── minio.Dockerfile
    ├── minio-artifacts.json
    ├── egress.Dockerfile
    ├── egress/
    │   ├── entrypoint.sh
    │   ├── squid.conf
    │   └── unbound.conf
    └── proxy/
        └── nginx.conf
```

`deploy/minio-artifacts.json` records the MinIO binary provenance; its digests are already embedded in the helper Dockerfile. `.dockerignore` keeps `.env` and other local files out of helper build contexts. The downloaded deployment files come from `main`, while `WEBMONITOR_IMAGE` selects the application release. For repeatable deployments, retain a reviewed copy of these files and pin the application image; old source tags may use an earlier Compose layout.

### 2. Create `.env`

Create `.env` in the deployment directory with at least these values:

```dotenv
# latest follows stable releases; replace with 1.0.0 to pin a version.
WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:latest
WEBMONITOR_HTTP_PORT=8080

APP_ORIGIN=http://localhost:8080
DEVELOPMENT_MODE=true

POSTGRES_PASSWORD=replace-with-a-strong-database-password
SECRET_KEY=replace-with-at-least-32-random-characters

ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-12-to-128-character-password

OPENAI_API_KEY=replace-with-your-model-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=replace-with-your-model-name
```

Replace every `replace-with-...` value before starting; these are placeholders, not credentials. Generate `SECRET_KEY` and the database password with a password manager or a command such as `openssl rand -hex 32`. The administrator password must be 12–128 characters. The account is created on first startup only when the users table is empty; otherwise create one later with `admin-create`.

`compose.yaml` defaults to `ghcr.io/webmonitor/webmonitor-agent:latest` and always pulls that image, but keeping `WEBMONITOR_IMAGE` explicit makes the chosen version visible. Pin `1.0.0` when you need a repeatable release; `latest` follows stable releases and changes over time.

Email alerts are optional. To enable them, add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `MAIL_FROM`. Exactly one of `SMTP_USE_SSL` and `SMTP_STARTTLS` must be `true`; match the mode supported by your mail provider.

### 3. Start and open

```sh
docker compose up -d --wait
```

The application image is pulled from GHCR. On the first start, Compose builds the `s3` and `egress` helper images from the downloaded Dockerfiles and pulls the upstream `postgres` and `nginx` images; this requires network access but does not download Chromium again. `--wait` returns after the health checks pass. If it fails, the stack is not ready: inspect `docker compose ps` and `docker compose logs` instead of assuming the deployment started.

The stack has six services:

| Service | Role |
| --- | --- |
| `api` | FastAPI, the scheduler, and every background loop: agent, HTTP collection, browser collection, and mail. |
| `web` | The Next.js frontend server. It uses the same image as `api`. |
| `proxy` | nginx on `127.0.0.1:8080` in front of the API and the frontend. |
| `postgres` | Application database. |
| `s3` | MinIO evidence storage for page archives and screenshots. |
| `egress` | Squid proxy that enforces the target policy and provides controlled outbound access. |

Open **[localhost:8080](http://localhost:8080/)** and sign in with the administrator email and password from `.env`. If no administrator was created, see [Create an administrator or invitation](#create-an-administrator-or-invitation).

Access is bound to the local machine by default. If you change `WEBMONITOR_HTTP_PORT`, update `APP_ORIGIN` to the same scheme, host, and port. Keep `DEVELOPMENT_MODE=true` for local HTTP; an `http://` origin is rejected otherwise. See the [configuration reference](https://github.com/webmonitor/WebMonitor-Agent/blob/main/.env.example) for all settings.

## Operate the stack

Run every command from the deployment directory. The normal installation has one `compose.yaml`, so no `-f` flags are required.

### Pull, start, inspect, and follow logs

```sh
docker compose pull api web
docker compose up -d --wait
docker compose ps
docker compose logs -f api web proxy
curl --fail http://localhost:8080/api/v1/health/ready
```

`docker compose restart api` restarts only the application process and leaves PostgreSQL and MinIO running. Stopping, restarting, or recreating those two containers discards their data; see [Data lifetime](#data-lifetime-upgrades-and-rollbacks).

### Create an administrator or invitation

The first startup creates an administrator only when `ADMIN_EMAIL` and `ADMIN_PASSWORD` are both set and the users table is empty. To create an administrator interactively at any time, for example when neither value was configured:

```sh
docker compose exec api webmonitor admin-create --email admin@example.com
```

The command prompts twice for a 12–128 character password. There is no default password.

To invite a member, issue a single-use, email-bound invitation link:

```sh
docker compose exec api webmonitor invite-create --email member@example.com --ttl-hours 24
```

The printed URL uses `APP_ORIGIN` and expires after the requested number of hours (1–168, default 24). An active administrator must already exist. If `REGISTRATION_ALLOWED_EMAILS` is non-empty, the invited address must also appear in that comma-separated list.

Recipients live in notification groups managed by an administrator. After signing in, create a group and add addresses; select that group when creating a monitor. A delivery status of `sent` means the mail server accepted the message; it does not confirm arrival in the recipient's inbox.

## Data lifetime, upgrades, and rollbacks

> **This deployment is temporary by design.** It declares no persistent volumes. Stopping, restarting, or recreating the PostgreSQL or MinIO container erases its data, including accounts, monitors, drafts, events, and saved page evidence. Restarting only `api` does not touch those containers.

The limits are explicit in `compose.yaml`: PostgreSQL data is a 512 MiB tmpfs, MinIO data is a 512 MiB tmpfs, and application containers get a 128 MiB `/tmp` tmpfs. Data therefore lasts only as long as those containers. There is no backup job, export command, or migration tool in the distributed files.

The schema is created on startup with SQLAlchemy `create_all`; there are no Alembic migrations. Existing databases are not migrated across releases, and schema compatibility between versions is not guaranteed.

### Upgrade

1. Change `WEBMONITOR_IMAGE` in `.env` to the new release tag.
2. Pull and recreate the application services.

```sh
docker compose pull api web
docker compose up -d --wait
```

An application-only image change may leave PostgreSQL running, but that does not make it a supported in-place upgrade. No migration path exists. If a release changes the schema, start from empty storage instead of carrying a previous database forward.

### Roll back

Set `WEBMONITOR_IMAGE` back to the previous tag, then run:

```sh
docker compose pull api web
docker compose up -d --wait
```

A rollback is subject to the same limits: no downgrade migration is provided, newer data may be incompatible, and any stop or recreation of the data containers erases it. For repeatable deployments, pin an exact version such as `1.0.0` and record that tag in your deployment configuration; `latest` follows stable releases and changes over time.

## Build from source

Source development is the only path that needs a repository checkout. The published-image installation above deliberately avoids it.

```sh
git clone https://github.com/webmonitor/WebMonitor-Agent.git
cd WebMonitor-Agent
```

Create `.env` using the template above; the checkout's `.env.example` lists the full development settings for reference. Then build and start with the build overlay:

```sh
docker compose -f compose.yaml -f compose.build.yaml up --build -d --wait
```

`compose.build.yaml` adds the application build; `compose.yaml` is the runtime definition used by the published image. Do not use the build overlay for a normal installation with the published image. For the development stack, keep both `-f` flags on later commands.

The build uses `deploy/Dockerfile`, installs Chromium, and takes several minutes. The resulting runtime image is not a frontend development environment: the `web` service contains the compiled Next.js standalone server and Node, not pnpm or the frontend source tree. Run frontend tooling outside the runtime container.

## Deployment boundary and limitations

The downloaded Compose stack is intended for local evaluation and development, not as a production platform. It binds the proxy to `127.0.0.1`, terminates no TLS, keeps all state in tmpfs, and provides no backups, migration path, high availability, or horizontal scaling. Put it behind your own TLS reverse proxy and operational controls if you expose it, and set `APP_ORIGIN` and `DEVELOPMENT_MODE` accordingly.

Functional limits:

- Targets must be public `http://` or `https://` URLs on ports 80 or 443. Private, loopback, link-local, metadata, and container-internal addresses are rejected.
- `TARGET_POLICY` defaults to `public`. `allowlist` and `any` require `DEVELOPMENT_MODE=true` and are intended for controlled environments such as the separate mocksite project; do not enable them for an Internet-facing deployment.
- Check intervals are 1 minute to 24 hours.
- Content inside iframes and Shadow DOM is not extracted. The preview reports these and other coverage limitations.
- Email is the only notification channel. Notification recipients are administrator-managed groups.
- The first successful check only establishes a baseline, and failed checks keep the last successful baseline. Previews never send email.
- Two services share the published image, but the `s3` and `egress` helper images and the nginx configuration are built or loaded from the downloaded files, not from that image.

## Release and versioning

- `main` is the development branch. Pushes build `:main` and `:sha-<short>` images; these are development artifacts, not releases, and never move `:latest`.
- The base `compose.yaml` defaults to `:latest` and pulls it on start. Set `WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:1.0.0` for a fixed version.
- A `vX.Y.Z` tag first verifies that the tag matches the versions declared in `pyproject.toml`, `src/webmonitor/__init__.py`, and `web/package.json`.
- Stable tags publish `:X.Y.Z`, `:X.Y`, and `:latest`, then create a GitHub Release. `latest` moves only for stable releases; a prerelease such as `v1.2.3-rc.1` never moves it.
- Images are built natively for `linux/amd64` and `linux/arm64` and merged into one multi-architecture manifest.
- The public package is `ghcr.io/webmonitor/webmonitor-agent`. The former `agent-api` and `agent-web` packages, including their `main` tags, have been removed; do not reference them.
- Bootstrap files are fetched from `main`. Record the reviewed deployment files alongside the chosen image version; changing the image tag alone does not update those files.

## About WebMonitor

WebMonitor-Agent is the actively developed WebMonitor product, built around conversational setup, preview and confirmation, and notifications based on your conditions.

If you prefer to enter an XPath directly to watch a page region, try the [original WebMonitor](https://github.com/webmonitor/WebMonitor). It supports public tasks and subscriptions and is maintained for fixes.

## License

[MIT](./LICENSE) — Use, modify, and distribute, including commercially, with the copyright and license notice retained.

Created by 秋风飘起黄叶落.
