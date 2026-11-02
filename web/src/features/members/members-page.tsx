"use client";
import { useState } from "react";
import { Check, Copy, UserPlus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/empty-state";
import { ListPagination } from "@/components/list-pagination";
import { PageBody, PageHeader } from "@/components/page-header";
import { ApiError } from "@/lib/api/client";
import {
  useCreateInvitation,
  useInvitations,
  useMembers,
  useSetMemberActive,
} from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/providers";

function MembersPanel() {
  const { t } = useI18n();
  const { errorText, formatDateTime } = useFormat();
  const { user } = useAuth();
  const members = useMembers();
  const setActive = useSetMemberActive();
  const items = members.data?.items ?? [];

  return (
    <section>
      <header className="mb-3">
        <h2 className="section-title">{t("activity.members.title")}</h2>
        <p className="meta mt-1 leading-5">{t("activity.members.description")}</p>
      </header>
      {members.isPending && <p className="meta">{t("common.loading")}</p>}
      {members.error && <p role="alert" className="text-sm text-error">{t("common.listError")}</p>}
      {setActive.error && (
        <p role="alert" className="text-sm text-error">{errorText(setActive.error)}</p>
      )}
      {!members.isPending && !members.error && items.length === 0 && (
        <EmptyState title={t("activity.members.emptyTitle")} />
      )}
      <ul className="divide-y border-t">
        {items.map((member) => {
          const self = member.id === user?.id;
          return (
            <li key={member.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2 text-[13px] font-medium">
                  <span className="truncate">{member.display_name}</span>
                  {member.role === "admin" && <Badge tone="neutral">{t("common.admin")}</Badge>}
                  {!member.active && <Badge tone="warning">{t("activity.members.disabled")}</Badge>}
                </p>
                <p className="num mt-0.5 truncate text-[11px] text-muted-foreground">{member.email}</p>
                <p className="num mt-0.5 text-[11px] text-muted-foreground">
                  {formatDateTime(member.created_at)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 shrink-0 px-2 text-xs text-muted-foreground"
                disabled={self || setActive.isPending}
                onClick={() => setActive.mutate({ userId: member.id, active: !member.active })}
              >
                {member.active ? t("activity.members.disable") : t("activity.members.enable")}
              </Button>
            </li>
          );
        })}
      </ul>
      <ListPagination query={members} />
    </section>
  );
}

function InvitationsPanel() {
  const { t } = useI18n();
  const { errorText, formatDateTime } = useFormat();
  const invitations = useInvitations();
  const create = useCreateInvitation();
  const [email, setEmail] = useState("");
  const [ttl, setTtl] = useState("24");
  const [created, setCreated] = useState<{ url: string; email: string } | null>(null);
  const [error, setError] = useState<{ code: string | null } | null>(null);
  const [copied, setCopied] = useState(false);
  const items = invitations.data?.items ?? [];

  async function invite() {
    setError(null);
    setCopied(false);
    try {
      const result = await create.mutateAsync({
        email: email.trim().toLowerCase(),
        ttlHours: Number(ttl),
      });
      setCreated({ url: result.url, email: result.email });
      setEmail("");
    } catch (failure) {
      setError({ code: failure instanceof ApiError ? failure.code : null });
    }
  }

  async function copy() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section>
      <header className="mb-3">
        <h2 className="section-title">{t("activity.invitations.title")}</h2>
        <p className="meta mt-1 leading-5">{t("activity.invitations.description")}</p>
      </header>

      <div className="space-y-3 rounded-[0.875rem] border bg-card p-4">
        <div className="space-y-1.5">
          <Label htmlFor="invite-email">{t("activity.invitations.email")}</Label>
          <Input
            id="invite-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@example.com"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="invite-ttl">{t("activity.invitations.ttl")}</Label>
          <Input
            id="invite-ttl"
            type="number"
            min={1}
            max={168}
            value={ttl}
            onChange={(event) => setTtl(event.target.value)}
          />
        </div>
        <Button
          size="sm"
          className="w-full"
          disabled={!email.trim() || !ttl || create.isPending}
          onClick={() => void invite()}
        >
          <UserPlus strokeWidth={1.5} />
          {create.isPending ? t("activity.invitations.creating") : t("activity.invitations.create")}
        </Button>
        {error && (
          <p role="alert" className="text-xs text-error">
            {error.code ? errorText(error.code) : t("format.operationFailed")}
          </p>
        )}
        {created && (
          <div className="space-y-1.5 border-t pt-3">
            <p className="meta">{t("activity.invitations.created", { email: created.email })}</p>
            <div className="flex items-start gap-2">
              <Input readOnly value={created.url} className="text-[11px]" />
              <Button variant="outline" size="sm" className="shrink-0 whitespace-nowrap" onClick={() => void copy()}>
                {copied ? <Check strokeWidth={1.5} /> : <Copy strokeWidth={1.5} />}
                {copied ? t("monitors.config.copied") : t("monitors.config.copy")}
              </Button>
            </div>
            <p className="meta">{t("activity.invitations.once")}</p>
          </div>
        )}
      </div>

      <h3 className="label-line mt-5">{t("activity.invitations.pending")}</h3>
      {invitations.isPending && <p className="meta mt-1">{t("common.loading")}</p>}
      {invitations.error && (
        <p role="alert" className="mt-1 text-sm text-error">{t("common.listError")}</p>
      )}
      {!invitations.isPending && !invitations.error && items.length === 0 && (
        <p className="meta mt-1">{t("activity.invitations.empty")}</p>
      )}
      <ul className="mt-1 divide-y border-t">
        {items.map((invitation) => (
          <li key={invitation.id} className="flex items-baseline justify-between gap-3 py-2">
            <span className="num min-w-0 truncate text-[12px]">{invitation.email}</span>
            <span className="num shrink-0 text-[11px] text-muted-foreground">
              {formatDateTime(invitation.expires_at)}
            </span>
          </li>
        ))}
      </ul>
      <ListPagination query={invitations} />
    </section>
  );
}

export function MembersPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  if (user && user.role !== "admin") {
    return (
      <div className="grid h-full place-items-center px-6 text-center">
        <div className="space-y-1.5">
          <p className="text-sm font-medium">{t("activity.members.adminOnlyTitle")}</p>
          <p className="meta">{t("activity.members.adminOnlyBody")}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto">
      <PageBody>
        <PageHeader
          title={t("common.members")}
          description={t("activity.members.pageDescription")}
        />
        <div className="grid items-start gap-10 lg:grid-cols-2 lg:gap-14">
          <MembersPanel />
          <InvitationsPanel />
        </div>
      </PageBody>
    </div>
  );
}
