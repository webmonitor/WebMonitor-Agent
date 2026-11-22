import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Every app route shares this frame: same max width, padding and title rhythm,
 * so switching between 对话, 事件 and 通知 does not move the content.
 */
export function PageBody({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("mx-auto w-full max-w-[80rem] px-6 py-8 sm:px-8 sm:py-10 lg:px-10", className)}>{children}</div>
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
    <header className="mb-8 flex flex-col gap-5 border-b border-hairline pb-6 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-2">
        <h1 className="page-title break-words">{title}</h1>
        {description && <div className="t-body-sm max-w-2xl text-muted-foreground">{description}</div>}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
