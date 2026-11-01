import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * An empty state is a line of text in the flow, not a framed box: a dashed
 * rectangle around two sentences reads as a missing component.
 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5 border-t pt-4", className)}>
      <p className="text-[13px] font-medium text-foreground">{title}</p>
      {description && <p className="meta max-w-md leading-5">{description}</p>}
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}
