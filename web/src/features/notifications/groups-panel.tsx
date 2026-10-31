"use client";
import { useState } from "react";
import { Plus, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/empty-state";
import { ApiError } from "@/lib/api/client";
import { useDeleteGroup, useGroups, useWriteGroup, type Group } from "@/lib/api/hooks";
import { useAuth } from "@/lib/providers";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ListPagination } from "@/components/list-pagination";

function memberText(members: Group["members"]): string {
  return members.map((member) => member.email).join("\n");
}

export function GroupsPanel() {
  const { user } = useAuth();
  const { t } = useI18n();
  const { errorText } = useFormat();
  const groups = useGroups();
  const write = useWriteGroup();
  const remove = useDeleteGroup();
  const [editing, setEditing] = useState<Group | "new" | null>(null);
  const [name, setName] = useState("");
  const [emails, setEmails] = useState("");
  const [error, setError] = useState<{ code: string | null } | null>(null);

  const admin = user?.role === "admin";
  const items = groups.data?.items ?? [];

  function openForm(group: Group | "new") {
    setEditing(group);
    setError(null);
    setName(group === "new" ? "" : group.name);
    setEmails(group === "new" ? "" : memberText(group.members));
  }

  async function save() {
    setError(null);
    const members = emails
      .split(/[\s,;]+/)
      .map((email) => email.trim().toLowerCase())
      .filter(Boolean)
      .map((email) => ({ email, active: true }));
    try {
      await write.mutateAsync({
        id: editing && editing !== "new" ? editing.id : undefined,
        body: {
          name: name.trim(),
          enabled: editing && editing !== "new" ? editing.enabled : true,
          members,
        },
      });
      setEditing(null);
    } catch (failure) {
      setError({ code: failure instanceof ApiError ? failure.code : null });
    }
  }

  return (
    <section className="space-y-3">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{t("activity.groups.title")}</h2>
          <p className="meta mt-0.5">{t("activity.groups.description")}</p>
        </div>
        {admin && (
          <Button
            size="sm"
            variant="outline"
            className="h-8 shrink-0 whitespace-nowrap"
            onClick={() => openForm("new")}
          >
            <Plus className="size-3.5" />
            {t("activity.groups.new")}
          </Button>
        )}
      </header>

      {groups.isPending && <p className="meta">{t("activity.groups.loading")}</p>}
      {remove.error && <p role="alert" className="text-xs text-error">{errorText(remove.error)}</p>}

      {!groups.isPending && !groups.error && items.length === 0 && (
        <EmptyState
          title={t("activity.groups.emptyTitle")}
          description={
            admin ? t("activity.groups.emptyAdmin") : t("activity.groups.emptyMember")
          }
        />
      )}

      <ul className="space-y-2">
        {items.map((group) => (
          <li key={group.id} className="surface-pad space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Users className="size-4 text-muted-foreground" />
                <span className="truncate text-[13px] font-medium">{group.name}</span>
                {!group.enabled && <Badge tone="neutral">{t("activity.groups.disabled")}</Badge>}
              </div>
              {admin && (
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-muted-foreground"
                    onClick={() => openForm(group)}
                  >
                    {t("activity.groups.edit")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-muted-foreground"
                    disabled={remove.isPending || !group.enabled}
                    onClick={() => remove.mutate(group.id)}
                  >
                    {t("activity.groups.disable")}
                  </Button>
                </div>
              )}
            </div>
            {group.members.length === 0 ? (
              <p className="meta">{t("activity.groups.noMembers")}</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {group.members.map((member) => (
                  <li key={member.email} className="chip bg-muted text-[11px] text-muted-foreground">
                    {member.email}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <ListPagination query={groups} />

      <Dialog open={editing !== null} onOpenChange={(value) => !value && setEditing(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editing === "new"
                ? t("activity.groups.form.newTitle")
                : t("activity.groups.form.editTitle")}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="group-name">{t("activity.groups.form.name")}</Label>
              <Input
                id="group-name"
                value={name}
                maxLength={200}
                onChange={(event) => setName(event.target.value)}
                placeholder={t("activity.groups.form.namePlaceholder")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="group-emails">{t("activity.groups.form.recipients")}</Label>
              <textarea
                id="group-emails"
                value={emails}
                rows={4}
                onChange={(event) => setEmails(event.target.value)}
                className="w-full rounded-lg border bg-card px-3 py-2 text-sm outline-none focus-visible:border-ring/60"
                placeholder={t("activity.groups.form.recipientsPlaceholder")}
              />
              <p className="meta">{t("activity.groups.form.recipientsHint")}</p>
            </div>
            {error && (
              <p className="text-xs text-error" role="alert">
                {error.code ? errorText(error.code) : t("activity.groups.saveFailed")}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
                {t("activity.groups.form.cancel")}
              </Button>
              <Button size="sm" onClick={() => void save()} disabled={!name.trim() || write.isPending}>
                {write.isPending ? t("activity.groups.form.saving") : t("activity.groups.form.save")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
