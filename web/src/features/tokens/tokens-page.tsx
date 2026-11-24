"use client";
import { useState } from "react";
import { Check, Copy, KeyRound, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/empty-state";
import { ListPagination } from "@/components/list-pagination";
import { PageBody, PageHeader } from "@/components/page-header";
import { mcpClientConfig, type McpClient } from "@/features/tokens/mcp-config";
import { useCreateToken, useRevokeToken, useTokens } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

const SCOPES = [
  "read",
  "discover",
  "drafts:write",
  "drafts:approve",
  "monitors:write",
  "events:write",
] as const;
const DEFAULT_SCOPES = SCOPES.filter((scope) => scope !== "drafts:approve");

const SCOPE_LABELS = {
  read: "tokens.scope.read",
  discover: "tokens.scope.discover",
  "drafts:write": "tokens.scope.drafts:write",
  "drafts:approve": "tokens.scope.drafts:approve",
  "monitors:write": "tokens.scope.monitors:write",
  "events:write": "tokens.scope.events:write",
} as const;

export function TokensPage() {
  const { t } = useI18n();
  const { errorText, formatDateTime } = useFormat();
  const tokens = useTokens();
  const create = useCreateToken();
  const revoke = useRevokeToken();
  const [name, setName] = useState("");
  const [ttl, setTtl] = useState("90");
  const [scopes, setScopes] = useState<string[]>([...DEFAULT_SCOPES]);
  const [created, setCreated] = useState<{ token: string; origin: string } | null>(null);
  const [client, setClient] = useState<McpClient>("cursor");
  const [copied, setCopied] = useState<"token" | "config" | null>(null);
  const items = tokens.data?.items ?? [];
  const config = created ? mcpClientConfig(client, created.origin, created.token) : "";

  async function submit() {
    setCopied(null);
    try {
      const result = await create.mutateAsync({
        name: name.trim(),
        scopes,
        ttl_days: ttl === "never" ? null : Number(ttl),
      });
      setCreated({ token: result.token, origin: window.location.origin });
      setName("");
    } catch {
      // The mutation exposes the structured API error below.
    }
  }

  async function copy(kind: "token" | "config") {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(kind === "token" ? created.token : config);
      setCopied(kind);
    } catch {
      setCopied(null);
    }
  }

  function toggleScope(scope: string) {
    setScopes((current) => current.includes(scope)
      ? current.filter((item) => item !== scope)
      : [...current, scope]);
  }

  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader title={t("common.tokens")} description={t("tokens.pageDescription")} />
        <div className="grid items-start gap-12 xl:grid-cols-2 xl:gap-16">
          <section>
            <header className="mb-3">
              <h2 className="section-title">{t("tokens.createTitle")}</h2>
              <p className="meta mt-1 leading-5">{t("tokens.createDescription")}</p>
            </header>
            <div className="space-y-4 rounded-lg border border-hairline bg-canvas p-5">
              <div className="space-y-1.5">
                <Label htmlFor="token-name">{t("tokens.name")}</Label>
                <Input
                  id="token-name"
                  value={name}
                  maxLength={200}
                  onChange={(event) => setName(event.target.value)}
                  placeholder={t("tokens.namePlaceholder")}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="token-ttl">{t("tokens.expiry")}</Label>
                <select
                  id="token-ttl"
                  className="flex h-9 w-full rounded-md border border-input bg-canvas px-3 text-sm text-ink"
                  value={ttl}
                  onChange={(event) => setTtl(event.target.value)}
                >
                  <option value="30">{t("tokens.days", { count: 30 })}</option>
                  <option value="90">{t("tokens.days", { count: 90 })}</option>
                  <option value="365">{t("tokens.days", { count: 365 })}</option>
                  <option value="never">{t("tokens.neverExpires")}</option>
                </select>
              </div>
              <fieldset className="space-y-2">
                <legend className="mb-2 text-sm font-medium text-ink">{t("tokens.scopes")}</legend>
                {SCOPES.map((scope) => (
                  <label key={scope} className="flex cursor-pointer items-start gap-2.5 text-sm">
                    <input
                      type="checkbox"
                      className="mt-0.5 size-4 accent-[var(--primary)]"
                      checked={scopes.includes(scope)}
                      onChange={() => toggleScope(scope)}
                    />
                    <span>
                      <code className="text-[13px] text-ink">{scope}</code>
                      <span className="ml-2 text-[13px] text-muted-soft">{t(SCOPE_LABELS[scope])}</span>
                    </span>
                  </label>
                ))}
              </fieldset>
              <Button
                className="w-full"
                disabled={!name.trim() || scopes.length === 0 || create.isPending}
                onClick={() => void submit()}
              >
                <KeyRound strokeWidth={1.5} />
                {create.isPending ? t("tokens.creating") : t("tokens.create")}
              </Button>
              {create.error && <p role="alert" className="text-sm text-error">{errorText(create.error)}</p>}
            </div>
          </section>

          <section>
            <header className="mb-3">
              <h2 className="section-title">{t("tokens.mcpTitle")}</h2>
              <p className="meta mt-1 leading-5">{t("tokens.mcpDescription")}</p>
            </header>
            <div className="space-y-4 rounded-lg border border-hairline bg-canvas p-5">
              <p className="text-[13px] leading-5 text-muted-soft">{t("tokens.mcpEnable")}</p>
              {created ? (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="created-token">{t("tokens.created")}</Label>
                    <div className="flex items-start gap-2">
                      <Input id="created-token" readOnly value={created.token} className="font-mono text-[12px]" />
                      <Button variant="outline" size="sm" className="shrink-0" onClick={() => void copy("token")}>
                        {copied === "token" ? <Check strokeWidth={1.5} /> : <Copy strokeWidth={1.5} />}
                        {copied === "token" ? t("monitors.config.copied") : t("monitors.config.copy")}
                      </Button>
                    </div>
                    <p className="meta">{t("tokens.once")}</p>
                  </div>
                  <div className="flex gap-2" aria-label={t("tokens.client")}>
                    <Button
                      variant={client === "cursor" ? "default" : "outline"}
                      size="sm"
                      onClick={() => { setClient("cursor"); setCopied(null); }}
                    >
                      Cursor
                    </Button>
                    <Button
                      variant={client === "claude" ? "default" : "outline"}
                      size="sm"
                      onClick={() => { setClient("claude"); setCopied(null); }}
                    >
                      Claude Desktop
                    </Button>
                  </div>
                  <p className="meta">{t(client === "cursor" ? "tokens.cursorHelp" : "tokens.claudeHelp")}</p>
                  <pre className="max-h-80 overflow-auto rounded-md border border-hairline bg-surface-soft p-3 text-[12px] leading-5 text-ink"><code>{config}</code></pre>
                  <Button variant="outline" size="sm" onClick={() => void copy("config")}>
                    {copied === "config" ? <Check strokeWidth={1.5} /> : <Copy strokeWidth={1.5} />}
                    {copied === "config" ? t("monitors.config.copied") : t("tokens.copyConfig")}
                  </Button>
                </>
              ) : (
                <p className="rounded-md border border-dashed border-hairline p-4 text-[13px] text-muted-soft">
                  {t("tokens.configAfterCreate")}
                </p>
              )}
            </div>
          </section>
        </div>

        <section className="mt-12">
          <header className="mb-3">
            <h2 className="section-title">{t("tokens.listTitle")}</h2>
            <p className="meta mt-1">{t("tokens.listDescription")}</p>
          </header>
          {tokens.isPending && <p className="meta">{t("common.loading")}</p>}
          {tokens.error && <p role="alert" className="text-sm text-error">{t("common.listError")}</p>}
          {revoke.error && <p role="alert" className="mb-2 text-sm text-error">{errorText(revoke.error)}</p>}
          {!tokens.isPending && !tokens.error && items.length === 0 && (
            <EmptyState title={t("tokens.empty")} />
          )}
          <ul className="border-t border-hairline divide-y divide-hairline">
            {items.map((token) => {
              const expired = token.expires_at !== null && new Date(token.expires_at).getTime() <= Date.now();
              const inactive = token.revoked_at !== null || expired;
              return (
                <li key={token.id} className="flex items-start justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">
                      <span>{token.name}</span>
                      <code className="text-[12px] font-normal text-muted-soft">{token.token_prefix}…</code>
                      {token.revoked_at && <Badge tone="neutral">{t("tokens.revoked")}</Badge>}
                      {expired && !token.revoked_at && <Badge tone="warning">{t("tokens.expired")}</Badge>}
                    </p>
                    <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-muted-soft">
                      <span>{t("tokens.createdAt", { date: formatDateTime(token.created_at) })}</span>
                      <span>{token.expires_at
                        ? t("tokens.expiresAt", { date: formatDateTime(token.expires_at) })
                        : t("tokens.neverExpires")}</span>
                      <span>{t("tokens.lastUsed", {
                        date: token.last_used_at ? formatDateTime(token.last_used_at) : t("tokens.notUsed"),
                      })}</span>
                    </p>
                    <p className="mt-1.5 flex flex-wrap gap-1.5">
                      {token.scopes.map((scope) => (
                        <code key={scope} className="rounded bg-surface-soft px-1.5 py-0.5 text-[11px] text-muted-soft">{scope}</code>
                      ))}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0 text-muted-soft hover:text-error"
                    disabled={inactive || revoke.isPending}
                    onClick={() => {
                      if (window.confirm(t("tokens.revokeConfirm", { name: token.name }))) {
                        revoke.mutate(token.id);
                      }
                    }}
                  >
                    <Trash2 strokeWidth={1.5} />
                    {t("tokens.revoke")}
                  </Button>
                </li>
              );
            })}
          </ul>
          <ListPagination query={tokens} />
        </section>
      </PageBody>
    </div>
  );
}
