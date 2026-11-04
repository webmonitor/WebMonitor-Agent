import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/*
 * A status pill: full radius, hairline edge and at most an 8-10% tint of its
 * own semantic color, so a row of them reads as labels rather than lights.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] leading-4 font-medium",
  {
    variants: {
      tone: {
        neutral: "border-hairline bg-canvas text-muted-foreground",
        brand: "border-primary/30 bg-primary/[0.08] text-primary-active",
        success: "border-success/30 bg-success/10 text-success-ink",
        warning: "border-warning/30 bg-warning/10 text-warning-ink",
        error: "border-error/25 bg-error/[0.07] text-error",
        outline: "border-hairline bg-transparent text-ink",
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
