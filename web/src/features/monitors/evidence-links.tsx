"use client";
import { formatBytes } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Reference = { kind: string; sha256: string; size_bytes: number };

/** Evidence stays one click from wherever a collected value is shown. */
export function EvidenceLinks({
  snapshotId,
  references,
  full = false,
}: {
  snapshotId?: string;
  references: Reference[];
  full?: boolean;
}) {
  const { t } = useI18n();
  if (!snapshotId || references.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
      {references.map((reference, index) => (
        <a
          key={reference.sha256}
          className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors duration-150 hover:text-foreground"
          href={`/api/v1/snapshots/${snapshotId}/evidence/${index}`}
          target="_blank"
          rel="noreferrer"
        >
          {reference.kind === "screenshot"
            ? full
              ? t("monitors.evidence.screenshotFull")
              : t("monitors.evidence.screenshot")
            : reference.kind === "json"
              ? t("monitors.evidence.json")
              : t("monitors.evidence.archive")}
          <span className="num">{formatBytes(reference.size_bytes)}</span>
        </a>
      ))}
    </div>
  );
}
