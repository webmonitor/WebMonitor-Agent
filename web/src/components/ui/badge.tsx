import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/*
 * A status tag, not a pill: 4px radius, no fill except a 10% tint of its own
 * semantic color, so a row of them reads as labels rather than lights.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-[0.25rem] border px-1.5 py-px text-[11px] leading-4 font-medium",
  {
    variants: {
      tone: {
        neutral: "border-border bg-transparent text-muted-foreground",
        brand: "border-primary/25 bg-primary/[0.06] text-primary",
        success: "border-success/25 bg-success/[0.07] text-success",
        warning: "border-warning/30 bg-warning/[0.07] text-warning",
        error: "border-error/25 bg-error/[0.07] text-error",
        outline: "border-border bg-transparent text-foreground",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
