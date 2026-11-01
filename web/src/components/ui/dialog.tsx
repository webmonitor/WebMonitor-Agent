"use client";
import type { ComponentProps } from "react";
import * as Primitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export const Dialog = Primitive.Root;
export const DialogTrigger = Primitive.Trigger;
export const DialogHeader = ({ className, ...props }: ComponentProps<"div">) => (
  <div className={`mb-4 space-y-1 ${className ?? ""}`} {...props} />
);
export const DialogTitle = Primitive.Title;

export function DialogContent({ className, children, ...props }: ComponentProps<typeof Primitive.Content>) {
  const { t } = useI18n();
  return (
    <Primitive.Portal>
      <Primitive.Overlay className="fixed inset-0 z-50 bg-[rgba(30,27,22,0.28)]" />
      <Primitive.Content
        className={`fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-[0.875rem] border bg-card p-6 shadow-[0_12px_40px_rgba(30,27,22,0.14)] ${className ?? ""}`}
        {...props}
      >
        {children}
        <Primitive.Close
          aria-label={t("common.close")}
          className="absolute right-3 top-3 rounded p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="size-4" />
        </Primitive.Close>
      </Primitive.Content>
    </Primitive.Portal>
  );
}
