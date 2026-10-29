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
import { errorText } from "@/lib/format";

function memberText(members: Group["members"]): string {
  return members.map((member) => member.email).join("\n");
}

export function GroupsPanel() {
  const { user } = useAuth();
  const groups = useGroups();
  const write = useWriteGroup();
  const remove = useDeleteGroup();
  const [editing, setEditing] = useState<Group | "new" | null>(null);
  const [name, setName] = useState("");
  const [emails, setEmails] = useState("");
  const [error, setError] = useState("");

  const admin = user?.role === "admin";
  const items = groups.data?.items ?? [];

  function openForm(group: Group | "new") {
    setEditing(group);
    setError("");
    setName(group === "new" ? "" : group.name);
    setEmails(group === "new" ? "" : memberText(group.members));
  }

  async function save() {
    setError("");
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
      setError(failure instanceof ApiError ? errorText(failure.code) : "保存没有成功，请重试。");
    }
  }

  return (
    <section className="space-y-3">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">通知组</h2>
          <p className="meta mt-0.5">监控按通知组发送邮件。改动收件人后，需要重新确认一次监控。</p>
        </div>
        {admin && (
          <Button
            size="sm"
            variant="outline"
            className="h-8 shrink-0 whitespace-nowrap"
            onClick={() => openForm("new")}
          >
            <Plus className="size-3.5" />
            新建
          </Button>
        )}
      </header>

      {groups.isPending && <p className="meta">正在加载…</p>}

      {!groups.isPending && items.length === 0 && (
        <EmptyState
          title="还没有通知组"
          description={admin ? "先建一个通知组，创建监控时就能选择收件人。" : "请联系管理员创建通知组。"}
        />
      )}

      <ul className="space-y-2">
        {items.map((group) => (
          <li key={group.id} className="surface-pad space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Users className="size-4 text-muted-foreground" />
                <span className="truncate text-[13px] font-medium">{group.name}</span>
                {!group.enabled && <Badge tone="neutral">已停用</Badge>}
              </div>
              {admin && (
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-muted-foreground"
                    onClick={() => openForm(group)}
                  >
                    编辑
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs text-muted-foreground"
                    disabled={remove.isPending || !group.enabled}
                    onClick={() => void remove.mutateAsync(group.id)}
                  >
                    停用
                  </Button>
                </div>
              )}
            </div>
            {group.members.length === 0 ? (
              <p className="meta">没有收件人</p>
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

      <Dialog open={editing !== null} onOpenChange={(value) => !value && setEditing(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "新建通知组" : "编辑通知组"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="group-name">名称</Label>
              <Input
                id="group-name"
                value={name}
                maxLength={200}
                onChange={(event) => setName(event.target.value)}
                placeholder="例如：运维值班"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="group-emails">收件人</Label>
              <textarea
                id="group-emails"
                value={emails}
                rows={4}
                onChange={(event) => setEmails(event.target.value)}
                className="w-full rounded-lg border bg-card px-3 py-2 text-sm outline-none focus-visible:border-ring/60"
                placeholder={"每行一个邮箱，例如：\nops@example.com\nowner@example.com"}
              />
              <p className="meta">用换行、逗号或空格分隔。</p>
            </div>
            {error && (
              <p className="text-xs text-error" role="alert">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEditing(null)}>
                取消
              </Button>
              <Button size="sm" onClick={() => void save()} disabled={!name.trim() || write.isPending}>
                {write.isPending ? "正在保存…" : "保存"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
