"use client";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { DerivedDraft } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

export function DiagnoseButton({ monitorId, jobId }: { monitorId: string; jobId?: string }) {
  const { t } = useI18n();
  const { errorText } = useFormat();
  const router = useRouter();
  const cache = useQueryClient();
  const diagnosis = useMutation({
    mutationFn: () => {
      const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
      return api<DerivedDraft>(`/monitors/${monitorId}/diagnosis${query}`, { method: "POST" });
    },
    onSuccess: (result) => {
      void cache.invalidateQueries({ queryKey: ["conversations"] });
      void cache.invalidateQueries({ queryKey: ["conversation", result.conversation_id] });
      router.push(`/app?conversation=${result.conversation_id}`);
    },
  });

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={diagnosis.isPending}
        onClick={() => diagnosis.mutate()}
      >
        <Wrench strokeWidth={1.5} />
        {diagnosis.isPending ? t("diagnosis.preparing") : t("diagnosis.action")}
      </Button>
      {diagnosis.error && (
        <span role="alert" className="text-[13px] text-error">
          {t("diagnosis.error")}：{errorText(diagnosis.error)}
        </span>
      )}
    </span>
  );
}
