# WebMonitor-Agent

通过对话创建网页监控：真实页面分析、配置草稿、实际提取与邮件预览，经用户确认后定时采集；保留变化事件、运行记录和受权限保护的证据。

**这是本机开发部署，不是生产部署。** PostgreSQL 和 MinIO 数据使用 tmpfs；停止、重启或重建数据容器会丢失本轮开发数据。以下命令是使用说明，不代表本轮已经执行或通过验收。

## 启动

需要 Docker Engine 与 Docker Compose。Python、Chromium、Node 22 与前端构建均在镜像中完成；正常启动无需宿主 Node 或 Python。

1. 没有 `.env` 时从 `.env.example` 复制；已有文件不要覆盖。
2. 至少设置 `POSTGRES_PASSWORD`、`SECRET_KEY`（≥32 字符）与 `ADMIN_EMAIL` / `ADMIN_PASSWORD`。需要模型对话时再配置 `OPENAI_*`；需要邮件时再配置 SMTP。
3. 在仓库根运行：

```sh
docker compose up --build --wait
```

打开 **http://localhost:8080**。只有 Nginx 向宿主发布端口，且绑定 `127.0.0.1`；API、数据库、对象存储和采集代理不直接暴露。

服务只有六个：`proxy`、`web`、`api`、`postgres`、`s3`、`egress`。**`api` 一个进程同时运行 FastAPI 与后台循环**（调度、Agent、HTTP 采集、Browser 采集、邮件），进程之间只通过 PostgreSQL 行与租约协作；没有独立 worker、scheduler、mailer 进程，也没有 `init-db` 步骤。

首次启动时 `api` 自动建表，并在 `users` 为空时用 `.env` 的 `ADMIN_EMAIL` / `ADMIN_PASSWORD` 创建管理员。这不会同步或重置已有账户密码；修改 `.env` 对已存在的管理员无效。缺少任一变量时不会创建管理员。

可选：新增管理员或签发邀请。

```sh
docker compose exec api webmonitor admin-create --email <管理员邮箱>
docker compose exec api webmonitor invite-create --email <允许名单中的邮箱> --ttl-hours 24
```

`admin-create` 交互读取并确认 12–128 字符密码。邀请链接只输出一次，应通过可信方式交付；注册必须使用邀请对应邮箱，普通注册只获得 `member` 角色。会话与邀请在数据库只保存令牌摘要。

## 配置边界

配置示例见 `.env.example`；配置项只在 `src/webmonitor/config.py` 的 `Settings` 中定义，非法值在启动时失败（`SECRET_KEY` 长度、`APP_ORIGIN` 结构、`TARGET_POLICY` 组合、各项并发/上限 ≥1）。

- `APP_ORIGIN` 默认 `http://localhost:8080`；状态变更检查精确 Origin 与 `SECRET_KEY` 派生的签名 CSRF token，包括登录与注册。更改 `WEBMONITOR_HTTP_PORT` 时应同步修改 `APP_ORIGIN`。
- 本地 HTTP 必须显式启用 `DEVELOPMENT_MODE=true`；HTTPS 下 Cookie 使用 Secure，始终 HttpOnly、SameSite=Lax。
- 目标地址策略由配置决定：`TARGET_POLICY=public`（默认，仅公网 80/443）、`allowlist`（精确 `scheme://host[:port]`）、`any`。后两者要求 `DEVELOPMENT_MODE=true`，`allowlist` 还要求非空 `TARGET_ALLOWED_ORIGINS`。
- 模型使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`，通过 OpenAI-compatible **Chat Completions** 接入。容器访问宿主网关使用 `host.docker.internal`；只有配置主机为 `127.0.0.1`/`localhost` 时才转换主机部分，路径不变。可用 `OPENAI_CONTAINER_BASE_URL` 显式覆盖。
- SMTP 使用 `SMTP_*` 与 `MAIL_FROM`；SSL 和 STARTTLS 必须二选一，证书校验不关闭。`MAIL_TEST_TO` 只供验收，不会自动成为产品收件人。
- 数据库使用 `PG*` + `POSTGRES_PASSWORD`；证据使用 `S3_*`。没有凭据文件、没有运行时分角色数据库账号：单进程部署共用一个应用账号。
- 不给应用注入 IMAP 凭据。收件箱验收应另行只读执行，且必须区分 SMTP 接收与目标收件箱实际收到。

## 数据模型

十二张表，全部在 `src/webmonitor/models.py`：`users`、`sessions`、`invitations`、`conversations`、`messages`、`jobs`、`drafts`、`monitors`、`snapshots`、`events`、`notification_groups`、`email_deliveries`。

- 没有工作区/成员多租户层：单部署，权限由 `users.role`（`admin`/`member`）与资源 `user_id` 判定。
- 一张 `jobs` 表承载所有异步工作：`agent`、`analyze`、`preview`、`production`。它同时保存租约、尝试历史（`attempts`）、工具步骤（`steps`）与流式文本（`partial_text`），取代旧的 runs/attempts/collection_jobs/agent_runs/outbox。
- 部分唯一索引保证单飞：一个监控最多一个活动 `production` job，一个草稿版本最多一个活动 `preview` job，一个对话最多一个活动 `agent` job。
- 草稿保存完整 `spec`、`spec_hash`；预览是 `drafts.preview` 中的冻结 JSON（提取结果、覆盖率、证据引用、规则模拟、渲染邮件、收件人、过期时间）。
- 证据只以 JSON 引用（bucket/object_key/sha256）保存在快照与预览里，没有证据表。
- 建表使用 `metadata.create_all`，没有迁移路径，也没有 schema 指纹；readiness 只检查数据库可用与十二张表齐全。允许从空库重建。

## 已实现的业务边界

### 创建与审批

工作台是对话优先的三栏视图（对话列表 / 对话 / 上下文面板），不要求用户手填 CSS。模型只能基于实际分析提出字段、规则、覆盖范围和采集方式；现价与原价不明确时需要澄清。

- 保存草稿产生新 revision，并作废旧预览与在途预览 job。
- `preview_monitor` 真实执行采集、证据上传、规则模拟、收件人去重与包内模板渲染；预览有效期由 `PREVIEW_TTL_MINUTES` 决定。
- `request_creation` 只校验预览并返回 `awaiting_confirmation`；**真正的创建只经过 `POST /conversations/{id}/approve` 与 `services/drafts.publish_draft`**，重新校验所有权、revision、预览摘要、收件人与出口策略。
- 重复确认返回同一 `monitor_id`；编辑 spec 后再用旧 revision 确认返回 `stale_revision`；通知组变化返回 `preview_stale`。
- 审批没有签名令牌、没有 SDK checkpoint、没有续跑：一次 HTTP 确认即完成，进程重启不影响已提交的草稿与预览。

Agents SDK 固定为 0.22.3，使用单 Agent/Runner，不实现第二套工具循环。每次执行从最近 `AGENT_HISTORY_MESSAGES` 条消息重建上下文；模型执行受 `AGENT_MAX_TURNS`、`AGENT_TIMEOUT_SECONDS`、`AGENT_MAX_TOKENS` 约束；外部 tracing 默认禁用。应用额外检查真实流终止原因和完整工具 JSON，截断输出不释放工具调用。会话状态只来自轮询快照（存在活动 job 时 1 秒，否则 15 秒），没有 SSE。

### 采集与变化

- HTTP HTML 与真实 Playwright Chromium 共用提取、校验、差异与提交逻辑。
- 字段支持 text、number、money、date、boolean、url、list；仅 CSS 选择器和固定浏览器步骤，不执行用户/模型提供的 JS、XPath 或表达式。
- 数字使用 Decimal 和显式分隔符；货币、日期格式/时区、布尔匹配值必须明确。缺失不等于空字符串，重复业务键、历史非空变空或类型异常均失败。
- 浏览器步骤仅限有界等待、滚动和翻页；iframe/Shadow DOM 不提取并报告限制。无法证明全量时显示 bounded。列表 full 覆盖需要可核对的声明总数与完整位置证据；翻页或虚拟列表未证明完整时不能生成删除结论。
- 支持文本变化、关键词状态、数字绝对/百分比变化、阈值，以及列表新增/删除/更新。规则仅一层 all/any。
- 百分比参考**上次成功采集**，不是累计参考价；前值为零记录 `rule_undefined`。数字仅显示格式变化不产生数值更新事件。
- 首次成功建立基线，不发业务变化；此后每次成功均推进基线。持续状态只在 false→true 通知，变化类不会吞掉连续不同列表新增。
- 调度间隔 60–86400 秒；晚到周期合并，不无限补发。每用户 active 监控数受 `MAX_ACTIVE_MONITORS` 限制。

采集必须经过 Squid 实际连接 ACL，拒绝私网、loopback、link-local、metadata、异常端口与不安全重定向；Collector 没有直连公网路由。HTTP 限 5 MiB/30 秒/5 次重定向，压缩输出在展开分配前受限。浏览器为全新 context、UID 10001、`chromium_sandbox=True`、只读根文件系统、cap_drop ALL；限制 60 秒、100 请求、20 MiB、5 MiB DOM，进程内并发受 `BROWSER_CONCURRENCY` 限制。沙箱不可用返回 `browser_unavailable`，不降级成无沙箱。

公网 DNS 由同一 `egress` 容器内的 Unbound 通过验证证书的 DNS-over-TLS 转发给 Cloudflare/Quad9。Squid 对解析后的实际连接地址执行 ACL，HTTPS CONNECT 仅允许 443。mocksite overlay 让 Squid 改用 Docker DNS，并且只额外放行 `site:9000` 这一个来源；其余目标仍按公网 ACL 处理。

Playwright seccomp 基于[官方 Docker profile](https://github.com/microsoft/playwright/blob/v1.63.0/utils/docker/seccomp_profile.json)，增加用户 namespace 内 Chromium 所需的 `chroot` 调用许可；仍由内核检查 namespace capability，不给容器增加 capability。

### 运行、证据与通知

`jobs` 使用 90 秒租约、15 秒续租；过期租约在下次领取时记为一次失败尝试，并按 1/5 秒退避重排，超过 `MAX_ATTEMPTS` 才终止。提交锁定监控并比较 `status` 与 `spec_version`：暂停、改版或取消使旧结果无法提交。仅临时网络/存储故障重试；契约失败不盲重试。失败保留可信基线与错误码；同一未恢复故障不反复发邮件，恢复后与最后可信基线比较。

S3 上传成功后才写入证据引用。证据接口按引用索引返回：`/snapshots/{id}/evidence/{index}` 与 `/drafts/{id}/evidence/{index}`；HTML 以 `text/plain` 附件返回，不作为同源页面执行，截图为 PNG。快照与事件同事务提交。

管理员维护显式邮箱通知组，所有成员只读。两个组选中同一邮箱只创建一条 Delivery。投递前重新校验该邮箱仍在某个启用组中；全部撤权则 cancelled。修改通知组后必须重新真实预览并显式确认。

五类模板为 price_changed、list_changed、content_changed、run_failed、recovered，随 wheel 分发（`notifications/templates/`），StrictUndefined + 自动转义，没有模板表也没有模板页面。价格模板缺 `current_price` 会跳过该预览邮件并记录 `template_contract_failed`。预览邮件在无脚本 sandbox iframe 中展示。

`sent` 只表示 SMTP 接收。Message-ID 稳定，临时错误最多三次、60/300 秒退避，永久错误 failed；SMTP 接收后数据库提交丢失仍可能重发，不承诺 exactly-once。

**本次不提供自动修复、AI 模板生成/编辑/发布或外部 MCP。** 无空按钮、假成功入口；`/mcp` 与认证发现元数据路径返回 404。

## 服务与运行命令

| 服务 | 职责 |
| --- | --- |
| proxy | 唯一宿主入口，转发 `/api/v1/` 与页面 |
| web | Next.js 16 工作台 |
| api | FastAPI + 调度、Agent、HTTP/Browser 采集、邮件循环 |
| postgres / s3 | 本轮开发数据与私有证据 |
| egress | 页面请求唯一出口 |

```sh
docker compose ps
docker compose logs api web proxy
curl --fail http://localhost:8080/api/v1/health/live
curl --fail http://localhost:8080/api/v1/health/ready
# 只重启应用，保留数据库、证据与草稿
docker compose restart api
```

readiness 只检查 PostgreSQL 可用与十二张表齐全，不匹配返回 503；不自动迁移/删表。`WORKERS_ENABLED=false` 可只运行 API（例如排查接口问题）。

`docker compose stop` 会停止数据容器并丢弃 tmpfs。需要有意重建本轮开发数据时，确认无需保留后重建数据服务：

```sh
docker compose up -d --force-recreate postgres s3
docker compose up -d --wait
```

日常操作不要用 `down -v`；需要长期数据保留时必须另行设计持久部署。

MinIO 公共镜像在本环境无法拉取，经用户批准使用 `deploy/minio.Dockerfile` 从[同一官方 Release](https://github.com/minio/minio/releases/tag/RELEASE.2025-04-22T22-12-26Z)构建本地镜像；二进制 SHA-256、架构与来源在 `deploy/minio-artifacts.json`。

## 开发与测试

开发、部署和测试统一在 Docker 中运行；宿主只需要 Docker Engine / Compose。

```sh
# 全量回归：集成测试自建 wm_test_<hex> 一次性数据库，跑完只删除它自己创建的库
docker compose run --rm --entrypoint pytest api -q
docker compose run --rm --entrypoint pytest api tests/unit -q
```

不需要任何辅助脚本：`tests/integration/conftest.py` 在会话开始创建一次性数据库、建表、结束时 drop；设置了 `TEST_DATABASE_URL` 时直接使用该库（不会删除）。没有可达的 PostgreSQL 时集成测试 skip，单元测试照常运行。

依赖通过单一 `requirements.txt` 保留哈希校验（含运行时与开发依赖，因此同一镜像可直接跑测试）。不要在宿主创建 `.venv` 或使用 `uv sync` / `uv run` 安装、运行本项目。

依赖由 `pyproject.toml` 的精确 pin 决定，`requirements.txt` 生成方式：

```sh
docker compose run --rm --entrypoint uv api pip compile pyproject.toml --group dev --generate-hashes --python-version 3.12 --universal -o requirements.txt
```

`deploy/Dockerfile` 默认安装 Chromium。若构建网络无法访问 Playwright CDN（`cdn.playwright.dev` 被拒绝），使用
`docker compose build --build-arg INSTALL_BROWSER=0 api` 构建：HTTP 采集可用，浏览器采集会以
`browser_unavailable` 失败，不会静默降级。

前端使用 Node 22 与唯一 `web/pnpm-lock.yaml`（`packageManager` 固定 pnpm 10，镜像内 `pnpm install --frozen-lockfile`）；在运行中的 API 上生成类型：

```sh
docker compose run --rm --no-deps web pnpm run generate:api   # 需要可访问 /api/v1/openapi.json
```

项目测试仅发现 `tests/unit` 与 `tests/integration`，不执行 `reference/` 中第三方项目的测试。集成测试优先读 `TEST_DATABASE_URL`，否则用 `PG*`/`POSTGRES_PASSWORD` 自建一次性库，两者都没有时 skip。当前覆盖：出口策略与目标策略、请求契约、密码/邮箱/会话、令牌摘要、预览摘要敏感性、claim/续租/重排/取消、首次基线静默、变化事件与投递、失败保留基线、恢复通知、邀请单次使用、登录限流、发布幂等与预览失效。

## 与 mocksite 联调

本仓库不再自带任何目标站点，也不再自带验收脚本。可重复的真实采集验收统一指向独立仓库 `../mocksite`（一个进程两个监听端口：站点 `:9000`、管理 `:9001`），它自己负责页面、数据与确定性故障；本仓库只负责采集、差异、证据与通知。

mocksite 只把站点端口发布到 `127.0.0.1:9000`，容器内无法经宿主网关可靠到达（Docker Desktop 会把该名字解析成 IPv6，而 Squid 不支持优先 IPv4）。因此 `compose.mocksite.yaml` 把 `egress` 直接接到 mocksite 的 compose 网络，用其服务名 `site:9000` 访问，并同时把 `api` 的目标策略改为 `allowlist`：

```sh
# 1) 独立仓库启动站点（默认只发布 127.0.0.1:9000）
cd ../mocksite && docker compose up -d --wait && cd -

# 2) 叠加 overlay：只允许 http://site:9000
docker compose -f compose.yaml -f compose.mocksite.yaml up -d --no-build --wait

# 3) 真实模型密钥：分析、草稿、预览都要走真实模型
#    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL 见 .env
```

- `MOCKSITE_NETWORK`（默认 `mocksite_default`）指定要加入的 mocksite 网络；项目名不同时改这里。
- `MOCKSITE_TARGET_ORIGIN`（默认 `http://site:9000`）指定允许的来源；换成别的端口时一并修改。
- 该 overlay 下 Squid 用 Docker DNS 解析（`deploy/egress/squid.mocksite.conf`），只额外放行 `site:9000`；公网目标仍被 `allowlist` 拒绝。
- 回滚到公网目标：`docker compose up -d --no-build --force-recreate api egress`。

mocksite 当前页面是 `/static/notice`（静态）与 `/ssr/notice`（SSR），主金额节点 `#notice #current-fee`，执行日期 `#notice #effective-date`，其余金额/日期是干扰项。改数据用管理端口：

```sh
TOKEN=$(grep '^MOCKSITE_TOKEN=' ../mocksite/.env | cut -d= -f2-)
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:9001/_admin/state
curl -sS -X PATCH -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"business":{"notice":{"current_fee":"100.00"}}}' http://127.0.0.1:9001/_admin/state
curl -sS -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:9001/_admin/reset
```

联调闭环（本仓库实测过的顺序）：对话里让助手分析 `http://site:9000/static/notice` → 保存草稿 → 真实预览（含 `current_price` money/CNY 与 `effective_date`）→ 在工作台点“确认创建” → 首次成功只建基线 → 用 `_admin/state` 把 `current_fee` 改小 → 下一个周期产生一个 `price_changed` 事件并按通知组投递邮件。

注意金额字段的命名约定：价格邮件模板要求字段名为 `current_price`，其他名字的 money 字段不会生成价格邮件；预览现在会以 `template_contract_failed:price_changed` 警告提示，而不是等投递时才失败。
