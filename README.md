<h1 align="center">WebMonitor-Agent</h1>

<p align="center">
  <strong>Tell it what to watch. Get an email when it changes.</strong>
</p>

<p align="center">
  Describe the page in your own words. The assistant opens it, takes one real sample, and you confirm before any schedule starts.<br>
  After that it checks on time and emails you when your condition is met.
</p>

<p align="center">
  <a href="#install-in-three-steps">Quick start</a> ·
  <a href="#your-first-monitor">Your first monitor</a> ·
  <a href="#email-alerts">Email alerts</a> ·
  <a href="#faq">FAQ</a> ·
  <a href="#update-roll-back-and-your-data">Updates and data</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

## What it watches

| Situation | Say something like |
| --- | --- |
| Price drop | “Watch this page's price and email me when it drops 10%” |
| New announcement | “Tell me when a new notice appears on the announcement board” |
| Stock change | “Check the stock count daily and let me know when it changes” |
| Deadline | “Track the registration deadline on this page and tell me if it moves” |

A rule can watch text, a keyword appearing or disappearing, a number against a threshold, a percentage or absolute change, or new, updated and removed items in a list.

It checks public `http://` and `https://` pages on ports 80 or 443, every 1 minute to 24 hours. Pages behind a sign-in, and content inside iframes or Shadow DOM, are outside what the collector can read. The preview tells you when it only covers part of a page.

## Before you start

- Docker Engine with Docker Compose v2, on Linux, macOS or Windows.
- A model service that speaks OpenAI Chat Completions: API key, base URL, model name. The conversation cannot run without it.
- An SMTP mailbox if you want email alerts. Optional, but without it no mail leaves the machine.
- A page URL you can open in a private window without signing in.

## Install in three steps

You do not clone the repository. Make a folder, download the runtime files into it, add one `.env`, start once.

### 1. Download the deployment files

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

If a download fails the loop stops and names the file; run it again before starting. Keep every file — `compose.yaml` mounts the nginx, seccomp and egress files, and builds two small local helper images from the Dockerfiles:

```text
webmonitor-agent/
├── .dockerignore
├── .env
├── compose.yaml
└── deploy/
    ├── browser-seccomp.json
    ├── egress.Dockerfile
    ├── minio.Dockerfile
    ├── minio-artifacts.json
    ├── egress/
    │   ├── entrypoint.sh
    │   ├── squid.conf
    │   └── unbound.conf
    └── proxy/
        └── nginx.conf
```

### 2. Create `.env`

Create `.env` next to `compose.yaml` with these values:

```dotenv
# :latest follows stable releases. Pin a version such as 1.0.0 for repeatable installs.
WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:latest
WEBMONITOR_HTTP_PORT=8080

# The address you open in the browser. Keep the same port as above.
APP_ORIGIN=http://localhost:8080
DEVELOPMENT_MODE=true

# Database password and session signing key. Generate both; do not reuse.
POSTGRES_PASSWORD=replace-with-a-strong-database-password
SECRET_KEY=replace-with-at-least-32-random-characters

# The first account, created on first start when no user exists yet.
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-12-to-128-character-password

# Model service for the assistant. Any OpenAI Chat Completions endpoint works.
OPENAI_API_KEY=replace-with-your-model-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=replace-with-your-model-name

# Email alerts (optional). Rules are under "Email alerts" below.
# SMTP_HOST=
# SMTP_PORT=465
# SMTP_USERNAME=
# SMTP_PASSWORD=
# SMTP_USE_SSL=true
# SMTP_STARTTLS=false
# MAIL_FROM=
```

Replace every `replace-with-...` value; these are placeholders, not credentials. `openssl rand -hex 32` is enough for `SECRET_KEY` and the database password. The administrator password must be 12–128 characters.

If you leave `ADMIN_PASSWORD` empty, no account is created at startup; create one later with the command in the [FAQ](#faq).

Keep `DEVELOPMENT_MODE=true` while the address is plain `http://`; an `http://` origin is rejected otherwise. If you change `WEBMONITOR_HTTP_PORT`, change `APP_ORIGIN` to the same host and port. The full list of settings is in [`.env.example`](https://github.com/webmonitor/WebMonitor-Agent/blob/main/.env.example).

### 3. Start everything

```sh
docker compose up -d --wait
```

One command starts the whole stack: the application, its database, the evidence store, the proxy and an outbound proxy for page collection. It pulls the published image, builds the two helper images locally on the first run (network needed, Chromium is not downloaded again), and returns only when every service is up — the ones with health checks have passed them.

You should see a clean exit, and in `docker compose ps` no service restarting or exited. Then open **[http://localhost:8080](http://localhost:8080/)**.

If the command fails or a container stays unhealthy, the site is not ready: inspect `docker compose ps` and `docker compose logs` (append a service name to narrow it) instead of retrying blindly. `curl --fail http://localhost:8080/api/v1/health/ready` should answer `{"status":"ready"}`.

The site is published on `127.0.0.1` only, on the machine running Docker. Use that machine's browser, or an SSH tunnel from yours.

## Your first monitor

Sign in with the `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`. The first start creates that account automatically. If it was not created, see the [FAQ](#faq). The **EN / 中文** switch at the top of the sidebar changes the interface language.

### Create a notification group

**Notifications** → **Notification groups** → **New**. Give it a name, add recipients one per line (commas or spaces also work), then **Save**.

Only an administrator can create groups; members ask an administrator. Every monitor sends through a group, and a group can hold several addresses. If you later change a group's recipients, confirm the monitor again before the new list is used.

### Describe what you want

Click **New conversation** and type what you need, for example one of the sentences in [What it watches](#what-it-watches). Press Enter to send, Shift+Enter for a new line, and the square button to stop a run that is taking too long.

Two things happen next:

- The assistant opens the page and shows a work log — **View N steps** — listing what it did: read the page, checked your notification groups, prepared the settings.
- If a decision is missing (how often to check, when exactly to alert, who should receive the mail) it asks instead of guessing. Answer in the same conversation.

### Check the preview, then create

Before anything is scheduled, a confirmation card appears — in the right-hand column on a wide screen, inline in the chat on a narrow one. It shows:

- monitor name, check frequency, page host and timezone, and how long the preview stays valid
- **Extracted content** — the fields it read and their actual values on this page
- **Notify when** — the rule that will trigger an email
- **Recipients** — the addresses that will be notified
- **Page screenshot** / **Page archive** when the sample saved them
- **Preview notification email** — the real email body
- warnings such as “The check covers only part of the page”

If something is wrong, say so in the chat: the assistant takes a new sample and the card updates. **Preview again** samples the same settings again; **Take a sample** runs the first sample when none exists yet.

**Create monitor** is the click that starts scheduled checking. If the card has expired, preview again — a preview stays valid for 60 minutes.

### After it starts

- The monitor appears under **Monitors** in the left sidebar with its name and interval. Its page shows **Last check**, **Next check**, **Check frequency**, **Collection method**, then **Recent checks**, **Current content** and **Recent events**.
- **Pause** / **Resume** stops and restarts the schedule. **Check now** runs one check immediately.
- **Edit settings** opens the conversation that owns the monitor. Describe the change, review the new preview, then **Save changes**; saving rebuilds the baseline.
- **Events** lists everything detected, with **All** / **Unread** filters and **Mark as read**.
- **Notifications** → **Delivery log** lists each email: recipient, status, attempts, body, and the error if it failed.

The first successful check only records the starting content and sends no email; comparisons begin with the second check. Previews never send email. A failed check keeps the last successful content as the comparison baseline.

## Email alerts

Add these to `.env` and apply them:

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=alert@example.com
SMTP_PASSWORD=your-smtp-password
SMTP_USE_SSL=true
SMTP_STARTTLS=false
MAIL_FROM=WebMonitor <alert@example.com>
```

```sh
docker compose up -d --wait
```

Rules that matter:

- Exactly one of `SMTP_USE_SSL` and `SMTP_STARTTLS` must be `true`. Use the mode your provider documents; port 465 usually means SSL, port 587 usually means STARTTLS.
- `MAIL_FROM` must contain a real address, and most providers require it to match the account you sign in with.
- If the provider requires authentication, set both `SMTP_USERNAME` and `SMTP_PASSWORD`. Leaving one empty disables authentication.

There is no SMTP form inside the app — this file is the only place to configure it. Without it, monitors still run and events are still recorded; only deliveries fail, and **Delivery log** shows why.

`Sent` means the mail server accepted the message. Whether it reaches the inbox depends on the receiving side, so check spam first when a colleague says nothing arrived. Temporary delivery failures are retried up to three times; configuration errors are reported as failed straight away.

## FAQ

**The page does not load.**
In `docker compose ps`, the services with a health check must say `healthy` and none may be restarting or exited. `docker compose logs api web proxy` shows what stopped. If the port is taken, change `WEBMONITOR_HTTP_PORT` *and* `APP_ORIGIN` to the same port, then `docker compose up -d --wait`.

**I cannot open it from another computer.**
The site is bound to `127.0.0.1` on the Docker host by design. Open it there, or change the port binding in `compose.yaml` and set `APP_ORIGIN` to the address you will actually use. Put your own HTTPS proxy in front before exposing it to a network.

**Sign-in says the email or password is incorrect, or no administrator exists.**
Create one now:

```sh
docker compose exec api webmonitor admin-create --email admin@example.com
```

It asks twice for a 12–128 character password. `ADMIN_EMAIL` and `ADMIN_PASSWORD` only take effect on the very first start with an empty users table.

**How do I give a colleague access?**

```sh
docker compose exec api webmonitor invite-create --email member@example.com --ttl-hours 24
```

Send the printed link over a safe channel. It works once, is bound to that address, expires after 24 hours (1–168 allowed), and requires an existing administrator. The colleague opens it, sets a display name and a 12–128 character password.

**The chat says the target address is not allowed.**
Only public `http://` or `https://` pages on ports 80 or 443 are accepted. Intranet and localhost addresses, other ports, and pages that need a sign-in cannot be monitored.

**The sample is empty, or only part of the page.**
The assistant reads the HTML first and opens the page in a real browser when the data needs JavaScript. It still cannot read iframe or Shadow DOM content, anything behind a login, or pages that block automation. Coverage warnings on the preview card say when the read was partial; if the values there are empty, the monitor would have nothing to compare — describe the target more precisely, or choose another page or another value on it.

**Create monitor is greyed out.**
There is no valid preview yet: click **Take a sample**, or **Preview again** if it expired. If **Recipients** says “No recipients yet”, add addresses to a notification group first.

**No email arrived.**
Open **Notifications** → **Delivery log**. `Sent` means the server accepted it — check spam. `Failed` shows the SMTP error. A monitor's first check sends nothing by design. When checks keep failing, one failure email goes out for that cause, and one recovery email when checks succeed again.

**I changed the recipients but nothing happened.**
Recipients come from notification groups. After editing a group, confirm the monitor again with **Edit settings** → **Save changes**; the next successful check establishes a new baseline.

**How often can a monitor check?**
Between 1 minute and 24 hours. Short intervals mean more requests to the target site and more load on this machine.

**Can it watch a page I have to log in to?**
No. Collection uses no cookies or credentials of yours.

## Update, roll back, and your data

### Update

Set `WEBMONITOR_IMAGE` in `.env` to the new tag, for example `ghcr.io/webmonitor/webmonitor-agent:1.0.0`, then apply it:

```sh
docker compose pull api web
docker compose up -d --wait
```

`:latest` follows stable releases; a pinned version keeps an install repeatable. Deployment files come from `main`, so keep the copies you actually started with.

The stored data format is created at startup and is not migrated between versions. If a release changes it, start from empty storage instead of carrying an old database forward.

### Roll back

Set the previous tag in `.env` and run the same two commands. Older versions may not read data written by a newer one.

> **Your data lasts only as long as these containers.** The deployment uses no persistent volumes: the database and the evidence store are memory-backed. Stopping, restarting, or removing the `postgres` or `s3` container erases accounts, monitors, drafts, events, screenshots and page archives. That includes `docker compose down`, which removes the containers. `docker compose restart api` alone is safe. There is no backup job, export command or restore tool here — if the data matters, keep it elsewhere and rebuild from `.env`.

## Development

<details>
<summary>Build from source, image releases, internals</summary>

Source work is the only path that needs a checkout:

```sh
git clone https://github.com/webmonitor/WebMonitor-Agent.git
cd WebMonitor-Agent
cp .env.example .env
docker compose -f compose.yaml -f compose.build.yaml up --build -d --wait
```

Fill `.env` with the same values as above; `.env.example` lists every development setting. Keep both `-f` flags on later commands. The build installs Chromium and takes several minutes. The running `web` container contains only the compiled frontend server, so run frontend tooling outside it.

Pushes to `main` build `:main` and `:sha-<short>` development images. `vX.Y.Z` tags verify the version declared in `pyproject.toml`, `src/webmonitor/__init__.py` and `web/package.json`, publish `:X.Y.Z`, `:X.Y` and `:latest`, and create a release. The application image is built for `linux/amd64` and `linux/arm64` and runs both the API and the frontend; the two helper images are built locally from `deploy/`.

The stack is meant for local use — it binds to `127.0.0.1`, terminates no TLS, and keeps no durable state.

</details>

## License

[MIT](./LICENSE) — use, modify and distribute, including commercially, with the copyright and license notice retained.

Created by 秋风飘起黄叶落.
