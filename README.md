<h1 align="center">WebMonitor-Agent</h1>

<p align="center">
  <strong>用对话创建监控，让网页变化送达邮箱。</strong>
</p>

<p align="center">
  <a href="#功能">功能</a> ·
  <a href="#快速启动">快速启动</a> ·
  <a href="#创建第一个监控">创建第一个监控</a> ·
  <a href="./.env.example">配置示例</a> ·
  <a href="https://github.com/webmonitor/WebMonitor">旧版 WebMonitor</a>
</p>

WebMonitor-Agent 是一个可自托管的网页变化监控应用。提供网页地址，用自然语言描述要关注的内容，助手会分析页面、生成监控草稿并执行真实采集预览。确认后，系统按计划检查价格、库存、公告或列表更新，并在满足条件时发送邮件。

## 功能

- **对话创建** — 描述监控目标、检查频率和通知条件，无需手写选择器。
- **预览后启用** — 核对实际提取结果、采集范围、通知收件人与邮件样式，再确认创建。
- **多种变化规则** — 支持文本变化、关键词、数值变化与阈值，以及列表新增、删除和更新。
- **页面证据** — 使用 HTTP 或 Playwright Chromium 采集，保留页面存档；浏览器采集附带截图。
- **统一工作台** — 管理对话与监控，查看变化事件、运行状态和邮件投递记录。

基于 **Next.js · React · FastAPI · OpenAI Agents SDK · Playwright · PostgreSQL**。Docker Compose 统一运行前端、API、数据库、对象存储与代理；调度、采集和邮件任务由 API 进程内的后台循环执行。

## 快速启动

需要 Docker Engine 和 Docker Compose。Python、Node.js 与 Chromium 均在镜像中安装，宿主无需单独配置。

```sh
git clone https://github.com/webmonitor/WebMonitor-Agent.git
cd WebMonitor-Agent
cp .env.example .env
```

已有 `.env` 时保留原文件。编辑配置，至少设置：

- `POSTGRES_PASSWORD` — 数据库密码；未单独设置 `S3_ROOT_PASSWORD` 时，也用作对象存储密码。
- `SECRET_KEY` — 至少 32 字符的随机密钥。
- `ADMIN_EMAIL` — 初始管理员邮箱。
- `ADMIN_PASSWORD` — 初始管理员密码，长度为 12–128 字符。
- `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` — 用于对话创建的模型服务，需兼容 OpenAI Chat Completions。

首次启动会自动建表，并在用户表为空时创建管理员。修改这些配置不会重置已有账户。

`.env.example` 的模型地址指向本机网关，请按实际服务修改。容器内会将地址中的 `localhost` 或 `127.0.0.1` 转换为 `host.docker.internal`；也可用 `OPENAI_CONTAINER_BASE_URL` 单独指定容器访问地址。

需要邮件提醒时，配置 `SMTP_HOST`、`SMTP_PORT`、`SMTP_USERNAME`、`SMTP_PASSWORD` 和 `MAIL_FROM`，并根据邮件服务选择 SSL 或 STARTTLS：`SMTP_USE_SSL` 与 `SMTP_STARTTLS` 必须恰有一个为 `true`。

> **数据保留：** 默认 Compose 用于本机开发，PostgreSQL 和 MinIO 均使用 tmpfs。停止、重启或重建这两个数据容器会丢失账户、监控、历史记录和页面证据。长期使用前需配置持久存储与备份。

```sh
docker compose up --build -d --wait
```

打开 **[localhost:8080](http://localhost:8080/)**，使用管理员邮箱和密码登录。默认仅向本机发布此端口；调整 `WEBMONITOR_HTTP_PORT` 时，需同步修改 `APP_ORIGIN`。本地 HTTP 部署保留 `DEVELOPMENT_MODE=true`。

## 创建第一个监控

1. 如需邮件提醒，先由管理员在通知组中添加收件人。
2. 新建对话，提供网页地址并描述需求，例如：“每 10 分钟检查这个商品的当前价格，低于 200 元时发邮件通知我。”
3. 等待助手分析并完成真实预览，核对提取内容、变化规则、检查频率、采集范围和收件人。
4. 在确认卡片中点击“创建监控”。启用后可在工作台查看状态、暂停监控或通过对话修改配置。

首次成功采集只建立比较基线，不发送变化通知；后续采集满足规则时才产生事件。采集失败保留上次可信基线，预览本身不发送邮件。草稿修改、预览过期或收件人变化后，需要重新预览并确认。

检查间隔支持 1 分钟至 24 小时。默认仅允许采集公网 HTTP/HTTPS 页面，不接受本机或私网目标。列表采集会标明覆盖范围；只有确认完整覆盖时才判断条目删除。iframe 与 Shadow DOM 内的内容暂不支持提取。

邮件记录中的 `sent` 表示 SMTP 服务已接收，不代表目标收件箱已经收到。

## 开发与运行

日常查看状态、日志与数据库就绪情况：

```sh
docker compose ps
docker compose logs api web proxy
curl --fail http://localhost:8080/api/v1/health/ready
```

仅需重启应用时使用 `docker compose restart api`，可保留仍在运行的数据容器。就绪接口只检查数据库连接与表结构。

测试也在 Docker 中运行：

```sh
docker compose run --rm --entrypoint pytest api -q
docker compose run --rm --entrypoint pytest api tests/unit -q
```

默认情况下，集成测试创建并清理独立的一次性数据库；没有可达的 PostgreSQL 时会跳过。显式设置 `TEST_DATABASE_URL` 时会直接使用该数据库，应仅指向测试专用库。

配置定义见 [Settings](./src/webmonitor/config.py)，监控字段与规则见 [DraftSpec](./src/webmonitor/schemas/monitors.py)，接口契约见运行实例的 [OpenAPI JSON](http://localhost:8080/api/v1/openapi.json)。Python 依赖在 [pyproject.toml](./pyproject.toml) 中精确固定，使用 `uv pip compile --generate-hashes` 生成带哈希的 `requirements.txt`；前端使用 pnpm 和已提交的锁文件。

真实采集联调使用独立的 [mocksite](https://github.com/webmonitor/mocksite) 项目。先启动目标站点，再使用 [compose.mocksite.yaml](./compose.mocksite.yaml) 接入其 Docker 网络；默认网络为 `mocksite_default`，允许来源为 `http://site:9000`。该配置会将采集目标限制为 mocksite。

## 项目状态

这是 WebMonitor 当前持续开发的版本，围绕“对话分析 → 真实预览 → 用户确认 → 定时采集 → 变化通知”构建。[旧版 WebMonitor](https://github.com/webmonitor/WebMonitor) 保留 XPath 监控方式，仅作维护。

当前默认部署面向本机开发，数据库通过启动时建表初始化，尚无版本迁移机制。生产部署前需另行规划持久化、备份、HTTPS 与升级方式。

## 许可证

[MIT](./LICENSE) — 允许使用、修改和分发，包括商业用途；需保留版权与许可声明。

作者：秋风飘起黄叶落。
