"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Radar } from "lucide-react";
import { api, ApiError, safeReturnTo } from "@/lib/api/client";
import { useAuth } from "@/lib/providers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const MESSAGES: Record<string, string> = {
  invalid_credentials: "邮箱或密码不正确。",
  registration_failed: "邀请无效、已过期或与邮箱不匹配，请联系管理员。",
  rate_limited: "尝试次数过多，请稍后再试。",
  forbidden: "请求未获授权，刷新页面后再试。",
};

export function AuthForm({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const { refresh } = useAuth();
  const [invitation, setInvitation] = useState("");
  const [returnTo, setReturnTo] = useState("/app");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const captured = useRef(false);

  useEffect(() => {
    if (captured.current) return;
    captured.current = true;
    const url = new URL(window.location.href);
    setReturnTo(safeReturnTo(url.searchParams.get("returnTo")));
    if (register) {
      setInvitation(
        url.searchParams.get("invitation_token") ?? url.searchParams.get("token") ?? "",
      );
      // The invitation stays in memory only; the URL stops carrying it.
      url.searchParams.delete("invitation_token");
      url.searchParams.delete("token");
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
    }
  }, [register]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(event.currentTarget);
    try {
      await api(register ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
          ...(register
            ? { display_name: form.get("display_name"), invitation_token: invitation }
            : {}),
        }),
      });
      await refresh();
      router.replace(returnTo);
    } catch (failure) {
      setError(
        failure instanceof ApiError
          ? (MESSAGES[failure.code] ?? failure.message)
          : "无法连接服务，请稍后重试。",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center px-5 py-12">
      <Link className="flex items-center gap-2 self-center text-[15px] font-semibold" href="/">
        <Radar className="size-5 text-primary" />
        WebMonitor
      </Link>
      <section className="surface-pad mt-8 space-y-1">
        <h1 className="text-xl font-semibold">{register ? "接受邀请" : "登录"}</h1>
        <p className="meta">
          {register
            ? "请使用受邀邮箱注册。邀请链接仅可使用一次。"
            : "登录以管理监控和查看通知。"}
        </p>

        <form onSubmit={submit} className="mt-6 flex flex-col gap-3.5">
          {register && (
            <div>
              <Label htmlFor="display_name">显示名称</Label>
              <Input id="display_name" name="display_name" autoComplete="name" required maxLength={100} />
            </div>
          )}
          <div>
            <Label htmlFor="email">邮箱</Label>
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div>
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 12 : undefined}
              maxLength={128}
              required
            />
            {register && <p className="meta mt-1">密码长度为 12–128 个字符，请勿重复使用其他账户的密码。</p>}
          </div>
          {register && !invitation && (
            <p className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-xs text-warning">
              缺少邀请信息，请使用管理员提供的完整邀请链接。
            </p>
          )}
          {error && (
            <p className="text-sm text-error" role="alert">
              {error}
            </p>
          )}
          <Button type="submit" className="mt-1" disabled={pending || (register && !invitation)}>
            {pending ? "正在提交…" : register ? "创建账户" : "登录"}
            <ArrowRight />
          </Button>
        </form>

        <p className="mt-5 text-center text-xs text-muted-foreground">
          {register ? (
            <Link className="text-primary underline-offset-2 hover:underline" href="/login">
              已有账户？前往登录
            </Link>
          ) : (
            "注册账户请联系管理员获取邀请链接。"
          )}
        </p>
      </section>
    </main>
  );
}
