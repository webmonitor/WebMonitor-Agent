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
    <div className={cn("space-y-2 border-t border-hairline pt-5", className)}>
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {description && <p className="meta max-w-md">{description}</p>}
      {action && <div className="pt-2">{action}</div>}
    </div>
  );
}
