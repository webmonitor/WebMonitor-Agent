export const en = {
  "public.nav.aria": "Primary",
  "public.nav.workspace": "Open workspace",

  "public.hero.eyebrow": "Web change monitoring",
  "public.hero.titleLine1": "Watch one page.",
  "public.hero.titleLine2": "Mail when it changes.",
  "public.hero.body":
    "Paste a public URL and say which part has to change. It opens the page on the schedule you set and puts the value before and after into the mail. The first check only stores a baseline; nothing is sent.",
  "public.hero.cta": "Get started",
  "public.hero.secondaryCta": "See how it works",
  "public.hero.note": "Accounts are created by an administrator; you need an invitation link.",

  "public.sample.title": "Sample notification",
  "public.sample.badge": "List changed",
  "public.sample.product": "Open courses",
  "public.sample.url": "example.edu/courses",
  "public.sample.previousCount": "3 rows",
  "public.sample.currentCount": "4 rows",
  "public.sample.added": "New row",
  "public.sample.addedTitle": "Intro to Data Analysis",
  "public.sample.addedMeta": "30 seats · closes on October 8",
  "public.sample.schedule": "Checked every 10 minutes; emailed when a row appears.",


  "public.steps.title": "Monitors are made in a conversation",
  "public.steps.link.title": "Send the URL and the rule",
  "public.steps.link.body":
    "Send the assistant the URL and what counts as a change. Frequency, recipients and the mail template are set in the preview, and can be changed later.",
  "public.steps.preview.title": "Look at one real sample",
  "public.steps.preview.body":
    "The assistant opens the page once and shows the values it got, how much of the page that covers, and the mail it would send.",
  "public.steps.notify.title": "Confirm, then it runs on a schedule",
  "public.steps.notify.body":
    "The first check stores a baseline only. After that, each change that matches is recorded and mailed.",

  "public.features.title": "What the workspace shows",
  "public.features.history.title": "Change details and snapshots",
  "public.features.history.body":
    "Every check keeps a snapshot of the page. A change record lines up each field before and after.",
  "public.features.email.title": "Mail log",
  "public.features.email.body":
    "Who received it, when it went out, and why it did not.",
  "public.features.recipients.title": "Recipient groups",
  "public.features.recipients.body":
    "An administrator keeps the groups; one monitor can mail several. Editing a group means confirming the monitor again.",
  "public.features.control.title": "Manual runs",
  "public.features.control.body":
    "Pause, resume, or run a check now to see what the page says at this moment.",

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
  "public.nav.workspace": "进入工作台",

  "public.hero.eyebrow": "网页变化监控",
  "public.hero.titleLine1": "盯住一个网页",
  "public.hero.titleLine2": "变了就发邮件给你",
  "public.hero.body":
    "填一个公开网址，再说清哪一处变了才算改动。它按设好的频率打开页面，把改前和改后的值写进那封邮件。第一次采集只存基线，不发信。",
  "public.hero.cta": "开始使用",
  "public.hero.secondaryCta": "看看怎么用",
  "public.hero.note": "账号由管理员开通，需要邀请链接。",

  "public.sample.title": "通知示例",
  "public.sample.badge": "列表变化",
  "public.sample.product": "可报名课程",
  "public.sample.url": "example.edu/courses",
  "public.sample.previousCount": "上次 3 条",
  "public.sample.currentCount": "当前 4 条",
  "public.sample.added": "新增条目",
  "public.sample.addedTitle": "数据分析入门",
  "public.sample.addedMeta": "30 个名额 · 10 月 8 日截止",
  "public.sample.schedule": "每 10 分钟检查一次，列表出现新条目时通知。",


  "public.steps.title": "监控是一次对话做出来的",
  "public.steps.link.title": "发网址，说清看哪一处",
  "public.steps.link.body": "把网址和判断标准发给助手。频率、收件人、邮件模板都在预览里设，之后还能改。",
  "public.steps.preview.title": "先看一眼真实采集",
  "public.steps.preview.body": "助手打开页面采一次，显示抽到的值、覆盖到哪一部分，以及那封邮件长什么样。",
  "public.steps.notify.title": "确认后才开始定时",
  "public.steps.notify.body": "第一次采集只存基线。之后每次符合条件的变化记一条，并发邮件。",

  "public.features.title": "工作台里能看到的东西",
  "public.features.history.title": "改动详情和页面快照",
  "public.features.history.body": "每次检查都留一份快照；变化记录逐项对照改前与改后。",
  "public.features.email.title": "投递记录",
  "public.features.email.body": "谁收到了、什么时候发的、为什么没发出去。",
  "public.features.recipients.title": "收件人分组",
  "public.features.recipients.body": "收件人由管理员按组维护，一个监控可以同时发给几个组；改过组要重新确认。",
  "public.features.control.title": "随时手动检查",
  "public.features.control.body": "暂停、恢复，或者立刻跑一次，看看现在的内容。",

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
