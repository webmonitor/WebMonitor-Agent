import Link from "next/link";
import { ArrowRight, Check, FileSearch, History, MailCheck, Radar, ShieldCheck } from "lucide-react";

const steps = [
  {
    title: "说清楚要看什么",
    body: "价格、库存、公告，还是某个列表里有没有出现新条目。用平常的话描述就够了。",
  },
  {
    title: "先看一眼真实结果",
    body: "助手打开页面、试采集一次，把取到的内容、收件人和邮件样式摆在你面前。",
  },
  {
    title: "确认后开始定时检查",
    body: "监控按你设定的节奏运行，发现变化时发邮件，并在工作台留下前后对照。",
  },
];

const features = [
  { icon: FileSearch, title: "确认前就有真实结果", body: "创建监控之前就能看到这次采集到的内容，不是猜测，也不会创建了才发现取不到。" },
  { icon: History, title: "变化有前后对照", body: "每个事件都记录改动前后的值和当时的页面存档，回看时不用凭记忆。" },
  { icon: MailCheck, title: "邮件有据可查", body: "谁收到了、什么时候发的、失败原因是什么，都留在投递记录里。" },
  { icon: ShieldCheck, title: "采集范围受控", body: "只有被允许的站点会被访问，内网地址和元数据端点一律拒绝。" },
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
            打开工作台
            <ArrowRight className="size-3.5" />
          </Link>
        </div>
      </nav>

      <section className="grid gap-10 py-14 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-center lg:py-20">
        <div>
          <h1 className="max-w-xl text-[2.1rem] font-semibold leading-[1.2] tracking-tight sm:text-[2.6rem]">
            网页一有变化，
            <br />
            邮件先到。
          </h1>
          <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
            用一句话说清要看的内容。WebMonitor 会先真实打开页面、确认能读到它，再由你决定是否开始定时监控。
            第一次采集只建立基准，所以你不会收到一封误报的邮件。
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <Link
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:opacity-90"
              href="/app"
            >
              开始使用
              <ArrowRight className="size-4" />
            </Link>
            <Link className="rounded-lg border bg-card px-4 py-2.5 text-sm hover:bg-muted" href="/login">
              我已有账户
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted-foreground">加入需要管理员发出的邀请链接。</p>
        </div>

        <div className="relative">
          <div className="surface-pad space-y-3 shadow-sm">
            <p className="text-xs text-muted-foreground">你说的</p>
            <p className="rounded-lg bg-accent px-3 py-2 text-[13px] text-accent-foreground">
              盯着这个页面的停车费，降价就发邮件给我。
            </p>
            <p className="text-xs text-muted-foreground">它先确认的</p>
            <ul className="space-y-1.5 text-[13px]">
              {[
                ["当前价格", "¥128.50"],
                ["执行日期", "10/31 16:00"],
                ["收件人", "2 人"],
              ].map(([label, value]) => (
                <li key={label} className="flex items-baseline justify-between gap-3">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="font-medium tabular-nums">{value}</span>
                </li>
              ))}
            </ul>
            <div className="flex items-center gap-1.5 rounded-lg border border-success/25 bg-success/10 px-3 py-2 text-xs text-success">
              <Check className="size-3.5" />
              预览通过，等你确认创建
            </div>
          </div>
        </div>
      </section>

      <section className="border-t py-10">
        <h2 className="text-sm font-semibold text-muted-foreground">三步开始</h2>
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

      <section className="grid gap-4 border-t py-10 sm:grid-cols-2">
        {features.map(({ icon: Icon, title, body }) => (
          <div key={title} className="surface-pad">
            <Icon className="size-4 text-primary" />
            <p className="mt-2 text-[15px] font-medium">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
          </div>
        ))}
      </section>

      <footer className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t py-4 text-xs text-muted-foreground">
        <span>WebMonitor · 网页变化监控</span>
        <span>私密部署 · 采集经由受控出口</span>
      </footer>
    </main>
  );
}
