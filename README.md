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
  <a href="#get-started">Get started</a> ·
  <a href="./.env.example">Configuration</a> ·
  <a href="./README.zh-CN.md">简体中文</a>
</p>

WebMonitor-Agent is a self-hosted web monitoring assistant. Paste a link and describe what matters, how often to check, and when to notify you. The assistant analyzes the page and prepares a monitor. You see the actual collection results before enabling it, without writing selectors yourself.

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
3. **Confirm and start.** Approve the monitor to begin scheduled checks. Review changes, pause or resume monitoring, and use conversation to adjust what you need.

The first successful scheduled check saves the starting content for later comparisons and sends no change notification. Previews do not send email either. Subsequent changes trigger alerts when they meet your rules.

## From a change to the details

- **Choose when to hear about it.** Set rules for text, keywords, numeric changes, thresholds, and new or updated list items. Removed items can also be tracked when complete list coverage is confirmed.
- **See the evidence.** Compare previous and current content and open the saved page from that check. Browser-based collection also captures a screenshot.
- **Notify the right people.** Select from notification groups maintained by the administrator. One monitor can notify multiple email addresses.
- **Keep track of activity.** Manage conversations, monitors, and events in one workspace, with recent check results and email delivery status. The interface is available in English and Chinese.
- **Review changes before applying them.** Preview and confirm monitor edits. Failed checks preserve the last successful content for future comparisons.

By default, monitoring supports public HTTP/HTTPS pages with check intervals from 1 minute to 24 hours. The preview explains what was actually collected and any coverage limitations. Content inside iframes or Shadow DOM is not currently supported.

## Get started

**Joining an existing instance?** Sign in at the address provided by your administrator. New members need an invitation link issued by the administrator.

**Hosting your own?** You need Docker Engine, Docker Compose, and a model service compatible with OpenAI Chat Completions. Email alerts also require an SMTP service. Images are published for `linux/amd64` and `linux/arm64`.

### Run the released image

```sh
git clone https://github.com/webmonitor/WebMonitor-Agent.git
cd WebMonitor-Agent
cp .env.example .env
```

The checkout supplies `compose.yaml`, the reverse-proxy configuration and the browser seccomp profile; the application itself comes from GitHub Container Registry. Set these values in `.env` before starting:

| Setting | What to enter |
| --- | --- |
| `WEBMONITOR_IMAGE` | The release you want, e.g. `ghcr.io/webmonitor/webmonitor-agent:1.0.0`; leave it empty to build from source instead |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Your initial administrator email and password; the password must be 12–128 characters |
| `SECRET_KEY` | A random key of at least 32 characters |
| `POSTGRES_PASSWORD` | Your database password |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Your model service's API key, endpoint, and model name |

Replace the example model endpoint and name with those of your service. The first startup creates an administrator when there are no users. Changing these settings does not reset existing accounts.

```sh
docker compose -f compose.yaml -f compose.ghcr.yaml up -d --wait
```

The two application services share one image: `api` runs the FastAPI server and every background loop, `web` runs the Next.js frontend. `docker compose pull` picks up the image; `docker compose up` alone keeps building from source.

<details>
<summary>Enable email alerts</summary>

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `MAIL_FROM` in `.env`. Choose SSL or STARTTLS to match your email provider: exactly one of `SMTP_USE_SSL` and `SMTP_STARTTLS` must be `true`.

After signing in, an administrator creates notification groups and adds recipients. Select a group when creating a monitor. A delivery status of `sent` means the mail server accepted the message; it does not confirm arrival in the recipient's inbox.

</details>

<details>
<summary>Build from source instead</summary>

```sh
docker compose up --build -d --wait
```

This builds `deploy/Dockerfile` locally, which downloads Chromium and takes several minutes. Development against a checkout still uses this path; `compose.ghcr.yaml` is only the released-image overlay.

</details>

> **Keep your data:** The included deployment is for local evaluation and development, with temporary database and page archive storage. Stopping, restarting, or recreating the PostgreSQL or MinIO containers loses their data, including accounts, monitors, and history. Configure persistent storage and backups before long-term use.

Open **[localhost:8080](http://localhost:8080/)**, sign in with the administrator email and password, and start your first conversation.

Access is local-only by default. If you change the port, update both `WEBMONITOR_HTTP_PORT` and `APP_ORIGIN`; keep `DEVELOPMENT_MODE=true` for local HTTP. See the [configuration example](./.env.example) for all settings.

## About WebMonitor

WebMonitor-Agent is the actively developed WebMonitor product, built around conversational setup, preview and confirmation, and notifications based on your conditions.

If you prefer to enter an XPath directly to watch a page region, try the [original WebMonitor](https://github.com/webmonitor/WebMonitor). It supports public tasks and subscriptions and is maintained for fixes.

## License

[MIT](./LICENSE) — Use, modify, and distribute, including commercially, with the copyright and license notice retained.

Created by 秋风飘起黄叶落.
