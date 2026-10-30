<h1 align="center">WebMonitor-Agent</h1>

<p align="center">
  <strong>告诉它看什么，让变化找到你。</strong>
</p>

<p align="center">
  关注价格、补货、公告与截止日期。<br>
  通过对话创建监控，预览确认后，让它按时检查并发送邮件。
</p>

<p align="center">
  <a href="#可以关注什么">使用场景</a> ·
  <a href="#如何使用">如何使用</a> ·
  <a href="#部署发布镜像">开始使用</a> ·
  <a href="#运维">运维</a> ·
  <a href="#数据寿命升级与回退">数据与升级</a> ·
  <a href="https://github.com/webmonitor/WebMonitor-Agent/blob/main/.env.example">配置参考</a> ·
  <a href="./README.md">English</a>
</p>

WebMonitor-Agent 是一个可自行部署的网页监控助手。粘贴链接，用自然语言说明关心的内容、检查频率和通知条件，助手会分析实时页面并准备监控。你可以先看到实际采集结果，再决定是否启用，无需手写选择器。后续定时检查会比较内容，并且只在命中规则时发送邮件。

## 可以关注什么

| 关注的内容 | 可以这样描述需求 |
| --- | --- |
| 价格变化 | “每 10 分钟检查这个商品，价格降到 200 元以下时通知我。” |
| 商品补货 | “关注这个商品的库存，从缺货变成有货时发邮件。” |
| 公告发布 | “每小时检查这个公告列表，有新公告就通知我。” |
| 日期调整 | “跟踪这个页面的报名截止日期，有变化就告诉我。” |

## 如何使用

1. **描述需求。** 新建对话，提供网页地址，告诉助手要看什么、多久检查一次、什么情况下通知。
2. **核对预览。** 助手打开页面并执行真实采集。确认提取内容、检查范围、通知规则、收件人和邮件样式是否符合预期。
3. **确认启用。** 点击创建监控后开始定时检查。后续可在工作台查看变化，暂停或恢复监控，也可通过对话调整需求。

首次成功检查会记录初始内容，作为后续比较的起点，不发送变化通知。预览也不会发送邮件；真正满足通知规则的后续变化才会触发提醒。

## 从发现变化到查看详情

- **按条件提醒。** 支持文本与关键词、数值变化与阈值、列表新增与更新；确认完整采集列表后，也可监控条目删除。
- **看清变化依据。** 对照变化前后的内容，查看当次检查保存的页面存档；浏览器采集还会留下截图。
- **通知需要的人。** 从管理员维护的通知组中选择收件人，一项监控可以通知多个邮箱。
- **掌握运行状态。** 在一个工作台管理对话、监控和事件，查看最近检查结果与邮件发送情况；界面支持中英文切换。
- **调整前先确认。** 修改监控后重新预览，确认结果再应用；采集失败时保留上一次成功的内容作为比较依据。

默认支持公网 HTTP/HTTPS 页面，检查间隔为 1 分钟至 24 小时。预览会说明本次实际采集的范围与限制；iframe 和 Shadow DOM 内的内容暂不提取。

## 运行要求

- Docker Engine 与 Docker Compose v2，可运行于 Linux、macOS 或 Windows。
- 兼容 OpenAI Chat Completions 的模型服务，用于对话。需要填写其 API 密钥、接口地址和模型名称。
- 如需邮件提醒，还需要可用的 SMTP 服务。
- 发布的应用镜像提供 `linux/amd64` 与 `linux/arm64` 两种架构。
- 使用发布镜像部署不需要 Git，也不需要克隆仓库。

## 部署发布镜像

WebMonitor-Agent 在 GitHub Container Registry 上发布一个应用镜像：

```text
ghcr.io/webmonitor/webmonitor-agent
```

同一个镜像包含 Python API 与后台任务、构建好的 Next.js 前端以及 Chromium。Compose 用不同入口把它运行成两个服务：`api` 与 `web`。镜像提供 `linux/amd64` 与 `linux/arm64` 两种架构：

```sh
docker pull ghcr.io/webmonitor/webmonitor-agent:latest
```

> **拉取不等于运行。** 上面的命令只确认公开镜像可以被匿名下载；它不会创建配置、启动 PostgreSQL 或证据存储、运行后台任务，也不会提供界面。可运行的部署还需要 `compose.yaml`、它挂载的 nginx 与 seccomp 文件、本地构建 `s3` 与 `egress` 辅助镜像所需的 Dockerfile，以及一个 `.env`。

正常安装会创建一个空部署目录，只下载这些运行文件；这条路径不要克隆仓库。

### 1. 下载运行文件

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

任一下载失败时循环会报错退出。请在所有文件就绪后再启动 Compose。

循环会按 `compose.yaml` 期望的目录结构下载：

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

`deploy/minio-artifacts.json` 记录 MinIO 二进制来源，其校验摘要已内置在辅助 Dockerfile 中。`.dockerignore` 可避免 `.env` 等本地文件进入辅助镜像构建上下文。部署文件来自 `main`，应用发布版本由 `WEBMONITOR_IMAGE` 单独选择。需要可重复部署时，请保留审阅后的部署文件并固定应用镜像；旧源码标签可能仍采用早期 Compose 布局。

### 2. 创建 `.env`

在部署目录中创建 `.env`，至少包含以下内容：

```dotenv
# latest 跟随稳定版发布；需要固定版本时改为 1.0.0。
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

启动前请替换所有 `replace-with-...` 占位值；它们只是示例，不是可用凭据。请用密码管理器或 `openssl rand -hex 32` 之类的命令生成 `SECRET_KEY` 和数据库密码。管理员密码必须为 12–128 字符。仅当首次启动时用户表为空才会创建该账户；否则可稍后用 `admin-create` 创建。

`compose.yaml` 默认使用 `ghcr.io/webmonitor/webmonitor-agent:latest`，并且每次启动都会拉取该镜像。仍然建议显式保留 `WEBMONITOR_IMAGE`，让实际使用的版本一目了然。需要可重复部署时固定 `1.0.0`；`latest` 会随稳定版发布移动。

邮件提醒是可选项。要启用，请在 `.env` 中加入 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD` 和 `MAIL_FROM`。`SMTP_USE_SSL` 与 `SMTP_STARTTLS` 必须恰有一个为 `true`，并按邮件服务支持的模式选择。

### 3. 启动并打开

```sh
docker compose up -d --wait
```

应用镜像从 GHCR 拉取。首次启动时，Compose 会用下载的 Dockerfile 在本地构建 `s3` 与 `egress` 辅助镜像，并拉取上游 `postgres` 与 `nginx` 镜像；这需要网络，但不会重新下载 Chromium。`--wait` 会在健康检查通过后返回。若命令失败，说明栈尚未就绪：请检查 `docker compose ps` 与 `docker compose logs`，不要假定部署已经启动。

整套栈包含六个服务：

| 服务 | 作用 |
| --- | --- |
| `api` | FastAPI、调度器以及全部后台循环：对话、HTTP 采集、浏览器采集和邮件。 |
| `web` | Next.js 前端服务，与 `api` 使用同一个镜像。 |
| `proxy` | nginx，监听 `127.0.0.1:8080`，转发 API 与前端请求。 |
| `postgres` | 应用数据库。 |
| `s3` | MinIO 证据存储，保存页面存档与截图。 |
| `egress` | Squid 代理，执行目标策略并提供受控的出站访问。 |

打开 **[localhost:8080](http://localhost:8080/)**，使用 `.env` 中的管理员邮箱和密码登录。若未创建管理员，请参阅[创建管理员或邀请](#创建管理员或邀请)。

默认仅绑定本机访问。更改 `WEBMONITOR_HTTP_PORT` 时，请把 `APP_ORIGIN` 同步改为相同的协议、主机和端口。本地 HTTP 部署需保留 `DEVELOPMENT_MODE=true`，否则 `http://` 源地址会被拒绝。完整配置见[配置参考](https://github.com/webmonitor/WebMonitor-Agent/blob/main/.env.example)。

## 运维

所有命令都在部署目录执行。正常安装只有一个 `compose.yaml`，因此不需要 `-f` 参数。

### 拉取、启动、检查与日志

```sh
docker compose pull api web
docker compose up -d --wait
docker compose ps
docker compose logs -f api web proxy
curl --fail http://localhost:8080/api/v1/health/ready
```

`docker compose restart api` 只重启应用进程，不会停止 PostgreSQL 和 MinIO。停止、重启或重建这两个容器会丢失数据，详见[数据寿命](#数据寿命升级与回退)。

### 创建管理员或邀请

首次启动只有在 `ADMIN_EMAIL` 与 `ADMIN_PASSWORD` 均已设置且用户表为空时创建管理员。若没有配置，可随时交互式创建：

```sh
docker compose exec api webmonitor admin-create --email admin@example.com
```

命令会两次提示输入 12–128 字符的密码；没有默认密码。

要邀请成员，请签发一个绑定邮箱、只能使用一次的邀请链接：

```sh
docker compose exec api webmonitor invite-create --email member@example.com --ttl-hours 24
```

打印出的链接基于 `APP_ORIGIN`，并在指定小时数后过期（1–168，默认 24）。系统中必须已有活跃管理员。若 `REGISTRATION_ALLOWED_EMAILS` 非空，被邀请地址还必须出现在该逗号分隔列表中。

收件人由管理员在通知组中维护。登录后创建通知组并添加邮箱，创建监控时再选择该通知组。投递记录中的 `sent` 表示邮件服务器已接收，不代表目标收件箱已经收到。

## 数据寿命、升级与回退

> **该部署按临时环境设计。** 它没有声明任何持久卷。停止、重启或重建 PostgreSQL 或 MinIO 容器会丢失其数据，包括账户、监控、草稿、事件和已保存的页面证据。仅重启 `api` 不会影响这两个容器。

`compose.yaml` 中的限制是明确的：PostgreSQL 数据位于 512 MiB 的 tmpfs，MinIO 数据位于 512 MiB 的 tmpfs，应用容器的 `/tmp` 为 128 MiB tmpfs。因此数据寿命等同于这些容器的寿命。分发的文件中没有备份任务、导出命令或迁移工具。

数据库结构在启动时通过 SQLAlchemy `create_all` 创建，没有 Alembic 迁移。现有数据库不会跨版本迁移，版本之间的 schema 兼容性也不作保证。

### 升级

1. 把 `.env` 中的 `WEBMONITOR_IMAGE` 改为新版本标签。
2. 拉取并重建应用服务。

```sh
docker compose pull api web
docker compose up -d --wait
```

仅更换应用镜像时 PostgreSQL 可能继续运行，但这并不构成受支持的原位升级；不存在迁移路径。如果新版本改变了数据库结构，应从空存储开始，不要把旧数据库带入新版本。

### 回退

把 `WEBMONITOR_IMAGE` 改回之前的标签，再执行：

```sh
docker compose pull api web
docker compose up -d --wait
```

回退同样受这些限制：没有降级迁移，较新版本写入的数据可能不兼容，停止或重建数据容器也会将其清空。需要可重复部署时，请固定 `1.0.0` 这样的确切版本，并在部署配置中记录该标签；`latest` 会随稳定版发布移动。

## 从源码构建

只有源码开发路径需要克隆仓库；上面的发布镜像安装有意不依赖仓库。

```sh
git clone https://github.com/webmonitor/WebMonitor-Agent.git
cd WebMonitor-Agent
```

按上面的模板创建 `.env`；仓库中的 `.env.example` 列出了完整的开发配置，可作参考。然后使用构建覆盖文件构建并启动：

```sh
docker compose -f compose.yaml -f compose.build.yaml up --build -d --wait
```

`compose.build.yaml` 为应用添加上构建配置；`compose.yaml` 是发布镜像使用的运行定义。正常使用发布镜像安装时不要加入该构建覆盖文件。开发栈后续命令需保留两个 `-f` 参数。

构建使用 `deploy/Dockerfile`，会安装 Chromium，耗时数分钟。构建出的运行镜像不是前端开发环境：`web` 服务只包含编译后的 Next.js standalone 服务与 Node，不包含 pnpm 或前端源码。前端工具应在运行容器之外使用。

## 部署边界与功能限制

下载得到的 Compose 栈面向本机试用与开发，不是生产平台。代理只绑定 `127.0.0.1`，不终止 TLS，全部状态位于 tmpfs，也没有备份、迁移路径、高可用或水平扩展。若要对外提供服务，应置于自己的 TLS 反向代理与运维控制之后，并相应设置 `APP_ORIGIN` 与 `DEVELOPMENT_MODE`。

功能限制：

- 目标必须是公网 `http://` 或 `https://` 地址，端口限 80 或 443。私有、环回、链路本地、元数据和容器内部地址都会被拒绝。
- `TARGET_POLICY` 默认为 `public`。`allowlist` 与 `any` 需要 `DEVELOPMENT_MODE=true`，只适用于受控环境（例如独立的 mocksite 项目）；不要在面向公网的部署中启用。
- 检查间隔为 1 分钟至 24 小时。
- iframe 和 Shadow DOM 内的内容不会被提取，预览会报告这些及其他采集范围限制。
- 邮件是唯一通知渠道；收件人来自管理员维护的通知组。
- 首次成功检查只建立基线，失败的检查保留上一次成功的基线；预览从不发送邮件。
- 两个服务共用发布镜像，但 `s3`、`egress` 辅助镜像与 nginx 配置由下载的文件构建或加载，不包含在该镜像中。

## 发布与版本策略

- `main` 是开发分支。推送到该分支会构建 `:main` 与 `:sha-<短哈希>` 镜像；它们是开发产物，不是发布版本，也永远不会移动 `:latest`。
- 基础 `compose.yaml` 默认使用 `:latest`，并在启动时拉取。需要固定版本时，设置 `WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:1.0.0`。
- 推送 `vX.Y.Z` 标签时，先校验标签与 `pyproject.toml`、`src/webmonitor/__init__.py`、`web/package.json` 中声明的版本是否一致。
- 稳定版标签发布 `:X.Y.Z`、`:X.Y` 和 `:latest`，并创建 GitHub Release。`latest` 只随稳定版移动；`v1.2.3-rc.1` 这类预发布版不会移动它。
- 镜像在 `linux/amd64` 与 `linux/arm64` 上原生构建，再合并为一个多架构 manifest。
- 公开包为 `ghcr.io/webmonitor/webmonitor-agent`。旧的 `agent-api`、`agent-web` 包（包括其 `main` 标签）已删除，不要继续引用。
- 引导文件来自 `main`。请同时记录审阅后的部署文件与所选镜像版本；只修改镜像标签不会更新这些文件。

## 关于 WebMonitor

WebMonitor-Agent 是 WebMonitor 当前持续开发的版本，采用对话创建、预览确认与按条件通知的使用方式。

如果你希望直接填写 XPath 来跟踪页面区域，可使用[原版 WebMonitor](https://github.com/webmonitor/WebMonitor)。原版支持公开任务与订阅，目前以维护和问题修复为主。

## 许可证

[MIT](./LICENSE) — 允许使用、修改和分发，包括商业用途；需保留版权与许可声明。

作者：秋风飘起黄叶落。
