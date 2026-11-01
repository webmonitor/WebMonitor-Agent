"use client";

import { useI18n } from "@/lib/i18n";

const OPTIONS = [
  { value: "en", label: "English", short: "EN" },
  { value: "zh-CN", label: "中文", short: "中文" },
] as const;

/** Segmented English / 中文 switch: two labels on a hairline, no pill, no lift. */
export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      role="group"
      aria-label={t("common.language")}
      className={`inline-flex shrink-0 items-center gap-0.5 rounded-md border border-transparent ${className}`}
    >
      {OPTIONS.map((option) => {
        const active = locale === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => setLocale(option.value)}
            className={`rounded px-1.5 py-0.5 text-[11px] leading-4 transition-colors duration-150 ${
              active
                ? "bg-secondary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span aria-hidden>{option.short}</span>
            <span className="sr-only">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}
