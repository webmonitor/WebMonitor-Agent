"use client";
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { useDeleteGroup, useGroups, useWriteGroup } from "@/lib/api/hooks";
import { useAuth } from "@/lib/providers";

export function GroupsPanel() {
  const { user } = useAuth();
  const groups = useGroups();
  const write = useWriteGroup();
  const remove = useDeleteGroup();
  const [name, setName] = useState("");
  const [emails, setEmails] = useState("");
  const [error, setError] = useState("");

  const admin = user?.role === "admin";
  const items = groups.data?.items ?? [];

  async function create() {
    setError("");
    const members = emails
      .split(/[\s,;]+/)
      .map((email) => email.trim().toLowerCase())
      .filter(Boolean)
      .map((email) => ({ email, active: true }));
    try {
      await write.mutateAsync({ body: { name: name.trim(), enabled: true, members } });
      setName("");
      setEmails("");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "保存失败，请重试。");
    }
  }

  return (
    <section className="space-y-3">
      <header>
        <h2>通知组</h2>
        <p className="text-xs text-muted-foreground">
          监控通过通知组决定收件人。修改群组后，已有监控需要重新预览才能确认新的收件人。
        </p>
      </header>

      {groups.isPending && <p className="text-sm text-muted-foreground">正在加载…</p>}
      {groups.error && <p className="text-sm text-error">{groups.error.message}</p>}

      <ul className="space-y-2">
        {items.map((group) => (
          <li key={group.id} className="rounded-xl border bg-card px-4 py-3 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium">
                  {group.name}
                  {!group.enabled && <span className="ml-2 text-xs text-muted-foreground">已停用</span>}
                </p>
                <p className="break-words text-xs text-muted-foreground">
                  {group.members.length === 0
                    ? "（无收件人）"
                    : group.members.map((member) => `${member.email}${member.active ? "" : "（停用）"}`).join("、")}
                </p>
              </div>
              {admin && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`停用通知组 ${group.name}`}
                  disabled={remove.isPending}
                  onClick={() => void remove.mutateAsync(group.id)}
                >
                  <Trash2 />
                  停用
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {items.length === 0 && !groups.isPending && (
        <p className="text-sm text-muted-foreground">还没有通知组。{admin ? "" : "请联系管理员创建。"}</p>
      )}

      {admin && (
        <div className="space-y-2 rounded-xl border border-dashed p-4">
          <p className="text-xs font-medium text-muted-foreground">新建通知组</p>
          <div>
            <Label htmlFor="group-name">名称</Label>
            <Input
              id="group-name"
              value={name}
              maxLength={200}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：运维值班"
            />
          </div>
          <div>
            <Label htmlFor="group-emails">收件人邮箱（逗号或换行分隔）</Label>
            <textarea
              id="group-emails"
              value={emails}
              rows={3}
              onChange={(event) => setEmails(event.target.value)}
              className="w-full rounded-lg border bg-card px-3 py-2 text-sm"
              placeholder="ops@example.com"
            />
          </div>
          <Button onClick={() => void create()} disabled={!name.trim() || write.isPending}>
            <Plus />
            创建
          </Button>
          {error && <p className="text-xs text-error" role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
