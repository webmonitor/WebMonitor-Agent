<h1 align="center">WebMonitor-Agent</h1>

<p align="center">
  <strong>说清要监控什么，预览确认后开始。</strong>
</p>

<p align="center">
  用一句话描述网页上你在意的内容。助手打开页面试采集一次，你确认之后再开始定时检查。<br>
  之后它按点运行，符合条件时发邮件给你。
</p>

<p align="center">
  <a href="#三步装好">快速开始</a> ·
  <a href="#第一次使用">第一次使用</a> ·
  <a href="#邮件提醒">邮件提醒</a> ·
  <a href="#常见问题">常见问题</a> ·
  <a href="#更新回退与数据保留">更新与数据</a> ·
  <a href="./README.md">English</a>
</p>

## 它能帮你盯什么

| 想关注的情况 | 可以这样输入 |
| --- | --- |
| 商品降价 | “监控这个页面的价格，降价 10% 时邮件提醒我” |
| 公告发布 | “关注公告栏有没有出现新的通知” |
| 库存变化 | “每天检查一次库存数量，有变化就告诉我” |
| 截止日期 | “跟踪这个页面的报名截止日期，有变化就告诉我” |

通知条件可以看一段文本，也可以看关键词出现或消失、数值超过阈值、涨跌幅、以及列表里新增、更新或消失的条目。

默认检查公网 `http://` / `https://` 页面（80 或 443 端口），间隔为 1 分钟到 24 小时。需要登录才能看的页面、iframe 和 Shadow DOM 里的内容目前采集不到；预览卡片会写明只覆盖了页面的一部分这类限制。

## 开始前需要准备

- Docker Engine 与 Docker Compose v2，Linux、macOS、Windows 都可以。
- 一个兼容 OpenAI Chat Completions 的模型服务：API 密钥、接口地址和模型名称，用于对话创建监控。
- 一个可用的 SMTP 邮箱（可选），用于发送邮件提醒。
- 一个复制到无痕窗口也能直接打开的网页地址。

## 三步装好

创建一个空目录，下载部署文件，按模板填写 `.env`，然后启动。

### 1. 下载部署文件

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

任何一次下载失败，循环会停下并告诉你缺哪个文件；再跑一次，等全部就位后继续。这些文件请全部保留：`compose.yaml` 会挂载 nginx、seccomp 和 egress 配置，并用下载到的 Dockerfile 在本地构建两个小辅助镜像。

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

### 2. 自建 `.env`

在 `compose.yaml` 旁边新建 `.env`，写入：

```dotenv
# :latest 跟随稳定版；需要可重复部署时改成 1.0.3 这样的固定版本。
WEBMONITOR_IMAGE=ghcr.io/webmonitor/webmonitor-agent:latest
WEBMONITOR_HTTP_PORT=8080

# 你在浏览器里打开的地址，端口要和上面一致。
APP_ORIGIN=http://localhost:8080
DEVELOPMENT_MODE=true

# 分别生成数据库密码与会话签名密钥。
POSTGRES_PASSWORD=replace-with-a-strong-database-password
SECRET_KEY=replace-with-at-least-32-random-characters

# 第一个账户。首次启动且系统里还没有用户时会自动创建。
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-12-to-128-character-password

# 助手使用的模型服务，任何 OpenAI Chat Completions 接口都可以。
OPENAI_API_KEY=replace-with-your-model-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=replace-with-your-model-name

# 邮件提醒（可选），规则见下面「邮件提醒」。
# SMTP_HOST=
# SMTP_PORT=465
# SMTP_USERNAME=
# SMTP_PASSWORD=
# SMTP_USE_SSL=true
# SMTP_STARTTLS=false
# MAIL_FROM=
```

把 `replace-with-...` 替换为自己的配置。`SECRET_KEY` 和数据库密码可分别用 `openssl rand -hex 32` 生成；管理员密码长度为 12–128 个字符。

`ADMIN_PASSWORD` 留空的话，启动时不会创建账户，之后可以用[常见问题](#常见问题)里的命令补建。

本地 `http://` 地址使用 `DEVELOPMENT_MODE=true`。修改 `WEBMONITOR_HTTP_PORT` 时，同步更新 `APP_ORIGIN` 的主机和端口。完整配置项见 [`.env.example`](https://github.com/webmonitor/WebMonitor-Agent/blob/main/.env.example)。

### 3. 一条命令启动

```sh
docker compose up -d --wait
```

命令会拉取应用镜像，首次运行时联网构建两个辅助镜像，启动配套服务并等待健康检查完成。

顺利时命令正常结束，`docker compose ps` 里没有服务在反复重启或已退出。然后打开 **[http://localhost:8080](http://localhost:8080/)**。

启动失败时，用 `docker compose ps` 查看服务状态，用 `docker compose logs` 查看错误；命令后可追加服务名。健康接口 `curl --fail http://localhost:8080/api/v1/health/ready` 正常返回 `{"status":"ready"}`。

站点只绑定在运行 Docker 这台机器的 `127.0.0.1` 上。用这台机器的浏览器打开，或者从你自己的机器建一条 SSH 隧道。

## 第一次使用

用 `.env` 里的 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 登录。首次启动会自动创建这个账户；如果没创建成功，见[常见问题](#常见问题)。侧栏顶部的 **EN / 中文** 可以切换界面语言。

### 先建一个通知组

**通知** → **通知组** → **新建**，填名称，收件人每行一个（用逗号或空格分隔也可以），点 **保存**。

通知组只有管理员能建，成员需要请管理员创建。监控通过通知组发信，一个组可以放多个邮箱。新增收件人后，每项监控都需要重新预览和确认。移除或停用成员、停用其已批准的通知组，会撤销待发送和后续邮件的对应授权来源；无关通知组不能恢复授权。同一监控批准过的其他通知组仍可为该地址提供授权。

### 描述你要什么

点 **新对话**，把需求写进去，例如[它能帮你盯什么](#它能帮你盯什么)里的句子。Enter 发送，Shift+Enter 换行；跑得太久就点方块按钮停止。

接下来会看到两件事：

- 助手打开页面，并出现一条 **查看 N 步操作** 的记录，说明它做了什么：读取页面、确认通知组、整理设置。
- 助手会在对话中询问需要补充的信息，例如检查频率、提醒条件和收件人。在同一对话中回答即可。

### 核对预览再创建

在开始定时检查之前，右侧（窄屏时在对话里）会出现一张确认卡片，包含：

- 监控名称、检查频率、页面地址和时区，以及这张预览的有效期
- **采集到的内容**：它读到的字段，以及这个页面上真实的取值
- **满足条件时通知**：触发邮件的规则
- **收件人**：会收到邮件的地址
- 采集时留下的 **页面截图** / **页面存档**
- **预览通知邮件**：真实邮件正文
- 只读到部分页面时的提醒，例如 **检查范围覆盖页面的一部分**

哪里不对就在对话里说，助手会重新采集一张新的卡片。**重新预览** 用同样的设置再采一次；还没有采集结果时点 **试采集一次**。

预览卡片会显示排队中、运行中或失败状态；失败原因会保留，可再次重试。创建或保存监控确认的是当前显示的这一份预览；如果它被另一份预览替换，需要刷新并重新确认。

**创建监控** 这一下才是开始定时检查的动作。卡片显示 **预览已过期** 时，先重新预览——一张预览的有效期是 60 分钟。

### 创建之后

- 左侧 **监控** 里出现这项监控，并显示它的检查间隔。点进去可以看到 **上次检查**、**下次检查**、**检查频率**、**采集方式**，往下是 **最近检查**、**当前内容** 和 **最近事件**。
- **暂停** / **恢复** 停下或继续计划；暂停会取消排队中或正在运行的采集，监控处于运行状态时才能 **立即检查**。
- **修改设置** 会打开一个带有现有监控完整配置的新对话。说清楚要改什么，核对新预览后点 **保存修改**；保存会更新原监控并重新建立基线。
- **事件** 汇总所有发现，可以切换 **全部** / **未读**，也可以 **标为已读**。
- **通知** → **投递记录** 列出每一封邮件：收件人、状态、尝试次数、正文，失败时还有原因。
- 对话、监控、检查记录、事件、通知组和投递列表均可通过 **加载更多** 访问较早记录。监控详情只显示该监控的事件。

第一次成功检查只记录起始内容，不发邮件；从第二次检查开始比较变化。预览从不发邮件。某次检查失败时，监控继续用上一次成功的内容作比较基线。

## 邮件提醒

把下面几行加进 `.env`，然后重新应用：

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=alert@example.com
SMTP_PASSWORD=你的 SMTP 密码
SMTP_USE_SSL=true
SMTP_STARTTLS=false
MAIL_FROM=WebMonitor <alert@example.com>
```

```sh
docker compose up -d --wait
```

几条关键规则：

- 按邮件服务商要求选择加密方式：`SMTP_USE_SSL` 与 `SMTP_STARTTLS` 中一个设为 `true`，另一个设为 `false`。465 通常使用 SSL，587 通常使用 STARTTLS。
- `MAIL_FROM` 填写发件地址，按服务商要求与登录账户保持一致。
- 需要身份认证时，同时填写 `SMTP_USERNAME` 和 `SMTP_PASSWORD`。

SMTP 在 `.env` 中配置。采集结果记录在事件页，邮件发送状态显示在 **投递记录** 中。

`已发送` 表示邮件服务器已接受邮件。未收到时可检查垃圾邮件。临时发送失败最多重试三次，配置错误显示为失败。

## 常见问题

**页面打不开。**
用 `docker compose ps` 检查服务状态，`docker compose logs api web proxy` 查看启动错误。端口被占用时，同步修改 `WEBMONITOR_HTTP_PORT` 和 `APP_ORIGIN`，再执行 `docker compose up -d --wait`。

**在另一台电脑上打不开。**
默认访问地址绑定 Docker 主机的 `127.0.0.1`。远程访问时，修改 `compose.yaml` 的端口绑定，并将 `APP_ORIGIN` 设为实际访问地址；对外服务时配置 HTTPS 反向代理。

**登录提示邮箱或密码不正确，或者根本没有管理员。**
现在补建一个：

```sh
docker compose exec api webmonitor admin-create --email admin@example.com
```

命令会两次提示输入 12–128 个字符的密码。`.env` 里的 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 只在首次启动、用户表为空时生效。

**怎么给同事开账号？**

```sh
docker compose exec api webmonitor invite-create --email member@example.com --ttl-hours 24
```

把打印出来的链接用可靠渠道发给对方。链接只能使用一次，绑定这个邮箱，24 小时后过期（可设 1–168 小时），并且系统中必须已有管理员。对方打开后设置显示名称和 12–128 个字符的密码。

**对话里说目标地址不在允许范围内。**
只接受公网 `http://` 或 `https://` 页面，端口限 80 或 443。内网和 localhost 地址、其他端口、需要登录的页面都不能监控。

**采集到的内容是空的，或者只有页面的一部分。**
助手先读 HTML，遇到需要 JavaScript 才出现的数据会改用浏览器打开页面。它仍然读不到 iframe 与 Shadow DOM 里的内容、登录之后的内容，以及拦截自动化的页面。预览卡片上的提醒会说明只读到了一部分；如果卡片里的值本身就是空的，监控就没有可比较的内容——把要关注的位置描述得更具体，或者换一个页面、换一个字段。

**创建监控按钮是灰的。**
还没有可用的预览：点 **试采集一次**；过期了就点 **重新预览**。如果 **收件人** 显示「还没有收件人」，先到通知组里加收件人。

**邮件没收到。**
打开 **通知** → **投递记录** 查看收件人、发送状态和错误信息。状态为 `已发送` 时检查垃圾邮件，状态为 `失败` 时按 SMTP 错误检查配置。首次检查建立比较基准；后续变化按规则通知。连续采集失败时，同一原因发送一次失败通知，恢复后发送恢复通知。

**改了收件人却没生效。**
收件人来自通知组。改完组之后，用 **修改设置** → **保存修改** 再确认一次监控；之后第一次成功检查会重建基线。

**检查频率能设多快？**
1 分钟到 24 小时。间隔越短，对目标站点的请求越多，这台机器的负载也越高。

**需要登录才能看的页面能监控吗？**
目前支持无需登录即可访问的公开页面。

## 更新、回退与数据保留

### 更新

把 `.env` 里的 `WEBMONITOR_IMAGE` 改成新版本标签，例如 `ghcr.io/webmonitor/webmonitor-agent:1.0.3`，然后应用：

```sh
docker compose pull api web
docker compose up -d --wait --no-deps api web
```

`:latest` 跟随稳定版；固定版本号才能让部署可重复。部署文件来自 `main` 分支，请保留你实际启动时用的那一份。

更新前记录当前镜像版本，并备份需要保留的数据。跨版本更新时核对数据库格式变化：项目不提供自动表结构迁移或降级。上面的命令只更新应用服务，保留仍在运行的数据库和证据存储服务。

### 回退

把 `WEBMONITOR_IMAGE` 改回上一个标签，执行上面的命令。使用与该版本匹配的数据；回退不会自动转换数据库结构。

默认数据库和证据存储使用临时内存目录。停止、重启或重建 `postgres`、`s3`，以及执行 `docker compose down`，会清空账户、监控、事件和页面证据。`docker compose restart api` 保留仍在运行的数据服务。长期使用前配置持久存储和备份，并保存 `.env` 与部署文件。

## 开发说明

<details>
<summary>从源码构建、镜像发布与内部结构</summary>

源码开发步骤：

```sh
git clone https://github.com/webmonitor/WebMonitor-Agent.git
cd WebMonitor-Agent
cp .env.example .env
docker compose -f compose.yaml -f compose.build.yaml up --build -d --wait
```

`.env` 按上面的说明填写，`.env.example` 列出了全部开发配置。后续命令都要保留两个 `-f` 参数。构建会安装 Chromium，耗时数分钟。运行中的 `web` 容器里只有编译好的前端服务，前端工具请在容器外使用。

推送 `vX.Y.Z` 标签发布版本。工作流核对应用版本，构建 `linux/amd64` 与 `linux/arm64` 镜像，发布 `:X.Y.Z`、`:X.Y` 并创建 GitHub Release；稳定版同时更新 `:latest`。Pull Request 仅构建，日常分支推送不触发镜像工作流。两个辅助镜像由 `deploy/` 下的文件在本地构建。

这套栈面向本机使用：只绑定 `127.0.0.1`，不做 TLS，不保存持久状态。

</details>

## 许可证

[CC BY-NC 4.0](./LICENSE) — 允许在署名、附上许可链接并注明修改的前提下分享与修改，仅限非商业用途。

作者：秋风飘起黄叶落。
