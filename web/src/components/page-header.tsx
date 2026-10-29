import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Every app route shares this frame: same max width, padding and title rhythm,
 * so switching between 对话, 事件 and 通知 does not move the content.
 */
export function PageBody({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("mx-auto w-full max-w-6xl px-5 py-6 sm:px-8", className)}>{children}</div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <h1 className="page-title truncate">{title}</h1>
        {description && <div className="meta max-w-2xl">{description}</div>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
