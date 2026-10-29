export const en = {
  "public.nav.aria": "Primary",
  "public.nav.login": "Sign in",
  "public.nav.workspace": "Open workspace",

  "public.hero.eyebrow": "Web change monitoring",
  "public.hero.titleLine1": "The changes you care about,",
  "public.hero.titleLine2": "deserve a closer look.",
  "public.hero.body":
    "Prices, stock, announcements, deadlines — tell WebMonitor what to watch. It opens the page on schedule and emails you what changed.",
  "public.hero.cta": "Get started",
  "public.hero.secondaryCta": "See how it works",
  "public.hero.note": "New users: contact your administrator for an invitation link.",

  "public.sample.title": "Sample notification",
  "public.sample.badge": "Price drop",
  "public.sample.product": "Product price updated",
  "public.sample.previous": "Previous price",
  "public.sample.current": "Current price",
  "public.sample.schedule": "Checked every 10 minutes; notified when the price drops.",

  "public.examples.title": "Common uses",
  "public.examples.price.title": "Price changes",
  "public.examples.price.detail":
    "Watch a product's price and get alerts on a drop percentage or target price.",
  "public.examples.restock.title": "Back in stock",
  "public.examples.restock.detail":
    "Watch stock status and get notified when an out-of-stock item is available again.",
  "public.examples.announcement.title": "New announcements",
  "public.examples.announcement.detail":
    "Track an announcement list and receive email when a new entry appears.",
  "public.examples.deadline.title": "Deadline changes",
  "public.examples.deadline.detail":
    "Monitor registration or payment deadlines and get notified when they move.",

  "public.steps.title": "Create monitors by chatting",
  "public.steps.link.title": "Share the page URL",
  "public.steps.link.body":
    "Paste the link into the chat and describe what to watch, how often to check, and when to notify you.",
  "public.steps.preview.title": "Review the preview",
  "public.steps.preview.body":
    "Check the extracted content and email preview, confirm the recipients, then create the monitor.",
  "public.steps.notify.title": "Get change notifications",
  "public.steps.notify.body":
    "The monitor runs on schedule. Changes that match your conditions become records and are emailed to you.",

  "public.features.title": "Manage monitors and notifications in the workspace",
  "public.features.history.title": "Inspect change details",
  "public.features.history.body":
    "Compare content before and after the update, and view the page snapshot saved for that check.",
  "public.features.email.title": "Check email delivery",
  "public.features.email.body":
    "See recipients, message body, and delivery results, including why a send failed.",
  "public.features.recipients.title": "Choose who gets notified",
  "public.features.recipients.body":
    "Pick recipients from groups your administrator configured; one monitor can notify several mailboxes.",
  "public.features.control.title": "Control the monitor",
  "public.features.control.body":
    "Pause or resume a monitor, or run a check right away to capture the current content.",

  "public.footer.tagline": "WebMonitor · Web change monitoring",

  "public.auth.login.title": "Sign in",
  "public.auth.login.description": "Sign in to manage monitors and view notifications.",
  "public.auth.register.title": "Accept invitation",
  "public.auth.register.description":
    "Register with the email that received the invitation. Each invitation link works once.",
  "public.auth.field.displayName": "Display name",
  "public.auth.field.email": "Email",
  "public.auth.field.password": "Password",
  "public.auth.passwordHint":
    "Passwords are 12–128 characters. Use a password unique to this account.",
  "public.auth.missingInvitation":
    "Invitation details are missing. Open the complete invitation link from your administrator.",
  "public.auth.submit": "Sign in",
  "public.auth.submitRegister": "Create account",
  "public.auth.submitting": "Submitting…",
  "public.auth.error.invalidCredentials": "Email or password is incorrect.",
  "public.auth.error.registrationFailed":
    "The invitation is invalid, expired, or does not match this email. Contact your administrator.",
  "public.auth.error.rateLimited": "Too many attempts. Try again later.",
  "public.auth.error.forbidden":
    "This request is not authorized. Refresh the page and try again.",
  "public.auth.error.network": "Cannot reach the service. Try again shortly.",
  "public.auth.hasAccount": "Already have an account? Sign in",
  "public.auth.noAccount": "To register, contact your administrator for an invitation link.",
} as const;

export const zh: Record<keyof typeof en, string> = {
  "public.nav.aria": "主导航",
  "public.nav.login": "登录",
  "public.nav.workspace": "进入工作台",

  "public.hero.eyebrow": "网页变化监控",
  "public.hero.titleLine1": "你关心的变化，",
  "public.hero.titleLine2": "值得被认真看见。",
  "public.hero.body":
    "价格、库存、公告、截止日期——告诉 WebMonitor 要看什么。它按时打开页面，把变化前后的内容发到你的邮箱。",
  "public.hero.cta": "开始使用",
  "public.hero.secondaryCta": "查看使用方式",
  "public.hero.note": "新用户请联系管理员获取邀请链接。",

  "public.sample.title": "通知示例",
  "public.sample.badge": "价格下降",
  "public.sample.product": "商品价格更新",
  "public.sample.previous": "上次价格",
  "public.sample.current": "当前价格",
  "public.sample.schedule": "每 10 分钟检查一次，价格下降时通知。",

  "public.examples.title": "常见用途",
  "public.examples.price.title": "价格变动",
  "public.examples.price.detail": "关注商品调价，按降价幅度或目标价格设置提醒。",
  "public.examples.restock.title": "商品补货",
  "public.examples.restock.detail": "关注库存状态，在缺货商品恢复有货时接收通知。",
  "public.examples.announcement.title": "公告发布",
  "public.examples.announcement.detail": "跟踪公告列表，发现新增条目时发送邮件。",
  "public.examples.deadline.title": "日期调整",
  "public.examples.deadline.detail": "监控报名、缴费等截止日期，变更后接收通知。",

  "public.steps.title": "通过对话创建监控",
  "public.steps.link.title": "提供网页地址",
  "public.steps.link.body": "在对话中粘贴链接，说明关注的内容、检查频率和通知条件。",
  "public.steps.preview.title": "检查预览结果",
  "public.steps.preview.body": "查看提取到的内容和邮件预览，核对收件人后确认创建。",
  "public.steps.notify.title": "接收变化通知",
  "public.steps.notify.body": "监控按设置运行。符合条件的变化会生成记录，并通过邮件通知。",

  "public.features.title": "在工作台管理监控与通知",
  "public.features.history.title": "查看变化详情",
  "public.features.history.body": "对比更新前后的内容，查看该次检查保存的页面存档。",
  "public.features.email.title": "检查邮件发送情况",
  "public.features.email.body": "查看收件人、邮件正文和发送结果，了解发送失败的原因。",
  "public.features.recipients.title": "设置通知对象",
  "public.features.recipients.body": "从管理员配置的通知组中选择收件人，一项监控可通知多个邮箱。",
  "public.features.control.title": "调整运行状态",
  "public.features.control.body": "可暂停或恢复监控，也可以立即执行一次检查，获取当前内容。",

  "public.footer.tagline": "WebMonitor · 网页变化监控",

  "public.auth.login.title": "登录",
  "public.auth.login.description": "登录以管理监控和查看通知。",
  "public.auth.register.title": "接受邀请",
  "public.auth.register.description": "请使用收到邀请的邮箱注册，每个邀请链接对应一次注册。",
  "public.auth.field.displayName": "显示名称",
  "public.auth.field.email": "邮箱",
  "public.auth.field.password": "密码",
  "public.auth.passwordHint": "密码长度为 12–128 个字符，建议为本账户单独设置密码。",
  "public.auth.missingInvitation": "缺少邀请信息，请使用管理员提供的完整邀请链接。",
  "public.auth.submit": "登录",
  "public.auth.submitRegister": "创建账户",
  "public.auth.submitting": "正在提交…",
  "public.auth.error.invalidCredentials": "邮箱或密码不正确。",
  "public.auth.error.registrationFailed": "邀请无效、已过期或与邮箱不匹配，请联系管理员。",
  "public.auth.error.rateLimited": "尝试次数过多，请稍后再试。",
  "public.auth.error.forbidden": "请求未获授权，刷新页面后再试。",
  "public.auth.error.network": "无法连接服务，请稍后重试。",
  "public.auth.hasAccount": "已有账户？前往登录",
  "public.auth.noAccount": "注册账户请联系管理员获取邀请链接。",
};
