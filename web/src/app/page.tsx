import Link from "next/link";
import { ArrowRight, History, MailCheck, Radar, Settings2, Users } from "lucide-react";

const examples = [
  { title: "价格变动", detail: "关注商品调价，按降价幅度或目标价格设置提醒。" },
  { title: "商品补货", detail: "关注库存状态，在缺货商品恢复有货时接收通知。" },
  { title: "公告发布", detail: "跟踪公告列表，发现新增条目时发送邮件。" },
  { title: "日期调整", detail: "监控报名、缴费等截止日期，变更后接收通知。" },
];

const steps = [
  { title: "提供网页地址", body: "在对话中粘贴链接，说明关注的内容、检查频率和通知条件。" },
  { title: "检查预览结果", body: "查看提取到的内容和邮件预览，核对收件人后确认创建。" },
  { title: "接收变化通知", body: "监控按设置运行。符合条件的变化会生成记录，并通过邮件通知。" },
];

const features = [
  { icon: History, title: "查看变化详情", body: "对比更新前后的内容，查看该次检查保存的页面存档。" },
  { icon: MailCheck, title: "检查邮件发送情况", body: "查看收件人、邮件正文和发送结果，了解发送失败的原因。" },
  { icon: Users, title: "设置通知对象", body: "从管理员配置的通知组中选择收件人，一项监控可通知多个邮箱。" },
  { icon: Settings2, title: "调整运行状态", body: "可暂停或恢复监控，也可以立即执行一次检查，获取当前内容。" },
];

export default function LandingPage() {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col px-6 py-6">
      <nav className="flex items-center justify-between gap-4">
        <span className="flex items-center gap-2 text-[15px] font-semibold">
          <Radar className="size-5 text-primary" />
          WebMonitor
        </span>
        <div className="flex items-center gap-2 text-sm">
          <Link className="rounded-lg px-3 py-1.5 text-muted-foreground hover:text-foreground" href="/login">
            登录
          </Link>
          <Link
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 font-medium text-primary-foreground hover:opacity-90"
            href="/app"
          >
            进入工作台
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      </nav>

      <section className="grid gap-10 py-14 lg:grid-cols-[minmax(0,1fr)_21rem] lg:items-center lg:py-20">
        <div>
          <p className="text-xs font-medium tracking-wide text-primary">网页变化监控</p>
          <h1 className="mt-2 max-w-xl text-[2.1rem] font-semibold leading-[1.25] tracking-tight sm:text-[2.5rem]">
            你关心的变化，
            <br />
            值得被认真看见。
          </h1>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-muted-foreground">
            价格、库存、公告、截止日期——告诉 WebMonitor 要看什么。它按时打开页面，
            把变化前后的内容发到你的邮箱。
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
              href="/app"
            >
              开始使用
              <ArrowRight className="size-4" />
            </Link>
            <Link className="rounded-lg border bg-card px-4 py-2.5 text-sm hover:bg-muted" href="#how-it-works">
              查看使用方式
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">新用户请联系管理员获取邀请链接。</p>
        </div>

        <div className="surface-pad space-y-5 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">通知示例</p>
            <span className="chip border-success/30 bg-success/10 text-success">价格下降</span>
          </div>
          <div>
            <p className="text-[15px] font-medium">商品价格更新</p>
            <p className="mt-1 text-xs text-muted-foreground">shop.example.com/product</p>
          </div>
          <dl className="grid grid-cols-2 gap-4">
            {[
              ["上次价格", "¥128.50"],
              ["当前价格", "¥99.00"],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="border-t pt-3 text-xs leading-relaxed text-muted-foreground">
            每 10 分钟检查一次，价格下降时通知。
          </p>
        </div>
      </section>

      <section className="border-t py-10">
        <h2 className="text-xl font-semibold">常见用途</h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {examples.map((example) => (
            <li key={example.title} className="surface space-y-2 p-5">
              <h3 className="text-[15px] font-medium">{example.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{example.detail}</p>
            </li>
          ))}
        </ul>
      </section>

      <section id="how-it-works" className="scroll-mt-6 border-t py-10">
        <h2 className="text-xl font-semibold">通过对话创建监控</h2>
        <ol className="mt-4 grid gap-6 sm:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title} className="space-y-1.5">
              <span className="grid size-7 place-items-center rounded-full border text-xs font-semibold tabular-nums text-primary">
                {index + 1}
              </span>
              <p className="text-[15px] font-medium">{step.title}</p>
              <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t py-10">
        <h2 className="text-xl font-semibold">在工作台管理监控与通知</h2>
        <div className="mt-5 grid gap-6 sm:grid-cols-2">
          {features.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-3">
              <Icon className="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <h3 className="text-[15px] font-medium">{title}</h3>
                <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t py-4 text-xs text-muted-foreground">
        <span>WebMonitor · 网页变化监控</span>
      </footer>
    </main>
  );
}
