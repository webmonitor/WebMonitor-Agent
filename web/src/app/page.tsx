import Link from "next/link";
import { Activity, MailCheck, Radio, ShieldCheck } from "lucide-react";

const features = [
  {
    icon: Radio,
    title: "先验证，再创建",
    body: "助手真实抓取目标页面，保存草稿并生成预览；只有你点击确认，监控才会被调度。",
  },
  {
    icon: Activity,
    title: "变化可追溯",
    body: "每次成功采集都会留下快照与证据文件，首次成功只建立基线，不会误报。",
  },
  {
    icon: MailCheck,
    title: "投递有记录",
    body: "邮件按通知组渲染与发送，每次尝试、SMTP 响应和失败原因都可查。",
  },
  {
    icon: ShieldCheck,
    title: "出站受控",
    body: "所有采集经由出站代理进行，内网地址与元数据端点被拒绝。",
  },
];

export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-5xl flex-col px-6 py-8">
      <nav className="flex items-center justify-between gap-4">
        <span className="flex min-w-0 items-center gap-2 text-base font-semibold sm:text-lg">
          <Radio className="size-5 text-primary" />
          观测 · WebMonitor
        </span>
        <div className="flex shrink-0 items-center gap-2 text-sm sm:gap-3">
          <Link className="whitespace-nowrap hover:underline" href="/login">登录</Link>
          <Link
            className="whitespace-nowrap rounded-lg bg-primary px-3 py-1.5 text-primary-foreground"
            href="/app"
          >
            进入工作台
          </Link>
        </div>
      </nav>

      <section className="flex-1 py-16">
        <p className="text-xs font-medium tracking-[0.2em] text-primary">CONVERSATIONAL MONITORING</p>
        <h1 className="mt-3 max-w-2xl text-balance">
          用一句话描述要监控的页面，<span className="text-primary">确认真实预览</span>后再开始。
        </h1>
        <p className="mt-4 max-w-xl text-muted-foreground">
          对话即配置：助手分析页面结构、提取字段、模拟规则并渲染邮件预览；监控创建后按计划采集，
          变化事件、证据和投递记录都留在这个工作台里。
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link className="rounded-lg bg-primary px-4 py-2 text-primary-foreground" href="/app">
            开始第一段对话
          </Link>
          <Link className="rounded-lg border px-4 py-2" href="/login">
            我已有账户
          </Link>
        </div>

        <dl className="mt-16 grid gap-6 sm:grid-cols-2">
          {features.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-xl border bg-card p-5">
              <Icon className="size-5 text-primary" />
              <dt className="mt-3 font-medium">{title}</dt>
              <dd className="mt-1 text-sm text-muted-foreground">{body}</dd>
            </div>
          ))}
        </dl>
      </section>

      <footer className="border-t pt-4 text-xs text-muted-foreground">
        首次使用需要管理员邀请。真实采集 · 明确确认 · 可追溯证据
      </footer>
    </main>
  );
}
