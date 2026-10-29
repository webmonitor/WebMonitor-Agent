"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Radar } from "lucide-react";
import { api, ApiError, safeReturnTo } from "@/lib/api/client";
import { useAuth } from "@/lib/providers";
import { useI18n } from "@/lib/i18n";
import { useFormat } from "@/lib/format";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const AUTH_ERROR_KEYS = {
  invalid_credentials: "public.auth.error.invalidCredentials",
  registration_failed: "public.auth.error.registrationFailed",
  rate_limited: "public.auth.error.rateLimited",
  forbidden: "public.auth.error.forbidden",
} as const;

type FormError = { code?: string; message?: string };

function errorKeyFor(code: string | undefined) {
  return code && code in AUTH_ERROR_KEYS
    ? AUTH_ERROR_KEYS[code as keyof typeof AUTH_ERROR_KEYS]
    : undefined;
}

export function AuthForm({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const { refresh } = useAuth();
  const { t } = useI18n();
  const { errorText: describeError } = useFormat();
  const [invitation, setInvitation] = useState("");
  const [returnTo, setReturnTo] = useState("/app");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
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
    setError(null);
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
          ? { code: failure.code, message: failure.message }
          : {},
      );
    } finally {
      setPending(false);
    }
  }

  const errorKey = errorKeyFor(error?.code);
  const errorText = error
    ? errorKey
      ? t(errorKey)
      : error.code
        ? describeError(error.code)
        : t("public.auth.error.network")
    : "";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center px-5 py-12">
      <div className="flex justify-end">
        <LanguageSwitcher />
      </div>
      <Link className="mt-2 flex items-center gap-2 self-center text-[15px] font-semibold" href="/">
        <Radar className="size-5 text-primary" />
        WebMonitor
      </Link>
      <section className="surface-pad mt-8 space-y-1">
        <h1 className="text-xl font-semibold">
          {t(register ? "public.auth.register.title" : "public.auth.login.title")}
        </h1>
        <p className="meta">
          {t(register ? "public.auth.register.description" : "public.auth.login.description")}
        </p>

        <form onSubmit={submit} className="mt-6 flex flex-col gap-3.5">
          {register && (
            <div>
              <Label htmlFor="display_name">{t("public.auth.field.displayName")}</Label>
              <Input id="display_name" name="display_name" autoComplete="name" required maxLength={100} />
            </div>
          )}
          <div>
            <Label htmlFor="email">{t("public.auth.field.email")}</Label>
            <Input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div>
            <Label htmlFor="password">{t("public.auth.field.password")}</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 12 : undefined}
              maxLength={128}
              required
            />
            {register && <p className="meta mt-1">{t("public.auth.passwordHint")}</p>}
          </div>
          {register && !invitation && (
            <p className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-xs text-warning">
              {t("public.auth.missingInvitation")}
            </p>
          )}
          {errorText && (
            <p className="text-sm text-error" role="alert">
              {errorText}
            </p>
          )}
          <Button type="submit" className="mt-1" disabled={pending || (register && !invitation)}>
            {pending
              ? t("public.auth.submitting")
              : t(register ? "public.auth.submitRegister" : "public.auth.submit")}
            <ArrowRight />
          </Button>
        </form>

        <p className="mt-5 text-center text-xs text-muted-foreground">
          {register ? (
            <Link className="text-primary underline-offset-2 hover:underline" href="/login">
              {t("public.auth.hasAccount")}
            </Link>
          ) : (
            t("public.auth.noAccount")
          )}
        </p>
      </section>
    </main>
  );
}
