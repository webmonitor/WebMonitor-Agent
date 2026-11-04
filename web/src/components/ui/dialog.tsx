"use client";
import type { ComponentProps } from "react";
import * as Primitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogHeader = ({ className, ...props }: ComponentProps<"div">) => (
  <div className={cn("mb-5 space-y-1.5", className)} {...props} />
);

/* Every dialog is a page fragment: cream canvas, serif title, hairline edge. */
export const DialogTitle = ({ className, ...props }: ComponentProps<typeof Primitive.Title>) => (
  <Primitive.Title
    className={cn("font-display text-[26px] font-normal leading-[1.15] tracking-[-0.02em] text-ink", className)}
    {...props}
  />
);

export function DialogContent({ className, children, ...props }: ComponentProps<typeof Primitive.Content>) {
  const { t } = useI18n();
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="fixed inset-0 z-50 bg-[rgba(20,20,19,0.32)]" />
      <Primitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-auto",
          "rounded-xl border border-hairline bg-canvas p-6 shadow-soft",
          className,
        )}
        {...props}
      >
        {children}
        <Primitive.Close
          aria-label={t("common.close")}
          className="absolute right-3 top-3 rounded-full p-1.5 text-muted-soft transition-colors hover:text-ink focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="size-4" />
        </Primitive.Close>
      </Primitive.Content>
    </Primitive.Portal>
  );
}
