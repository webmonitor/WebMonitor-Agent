"use client";
import { useState, type FormEvent } from "react";
import { Mail, Webhook } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTestDelivery, type NotificationTestResult } from "@/lib/api/hooks";
import { useFormat } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/providers";

type Channel = "email" | "webhook";

export function TestDelivery() {
  const { user } = useAuth();
  const { t } = useI18n();
  const { errorText } = useFormat();
  const test = useTestDelivery();
  const [channel, setChannel] = useState<Channel | null>(null);
  const [destination, setDestination] = useState("");
  const [result, setResult] = useState<NotificationTestResult | null>(null);

  if (user?.role !== "admin") return null;

  function openForm(next: Channel) {
    test.reset();
    setResult(null);
    setDestination("");
    setChannel(next);
  }

  function closeForm() {
    setChannel(null);
    setResult(null);
    test.reset();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!channel) return;
    setResult(null);
    try {
      setResult(await test.mutateAsync({ channel, destination: destination.trim() }));
    } catch {
      // The mutation exposes the sanitized server error below.
    }
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => openForm("email")}>
          <Mail strokeWidth={1.5} />
          {t("activity.testDelivery.email")}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => openForm("webhook")}>
          <Webhook strokeWidth={1.5} />
          {t("activity.testDelivery.webhook")}
        </Button>
      </div>

      <Dialog open={channel !== null} onOpenChange={(open) => !open && closeForm()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {channel === "webhook"
                ? t("activity.testDelivery.webhookTitle")
                : t("activity.testDelivery.emailTitle")}
            </DialogTitle>
          </DialogHeader>
          <form className="space-y-4" onSubmit={(event) => void submit(event)}>
            <p className="meta leading-5">{t("activity.testDelivery.description")}</p>
            <div className="space-y-1.5">
              <Label htmlFor="test-delivery-destination">
                {channel === "webhook"
                  ? t("activity.testDelivery.webhookDestination")
                  : t("activity.testDelivery.emailDestination")}
              </Label>
              <Input
                id="test-delivery-destination"
                type={channel === "webhook" ? "url" : "email"}
                value={destination}
                required
                maxLength={1000}
                autoFocus
                onChange={(event) => setDestination(event.target.value)}
                placeholder={channel === "webhook"
                  ? "https://hooks.example.com/ops"
                  : "ops@example.com"}
              />
            </div>
            {test.error && <p role="alert" className="text-[13px] text-error">{errorText(test.error)}</p>}
            {result && (
              <p role="status" className="text-[13px] text-success-ink">
                {t("activity.testDelivery.success", { code: result.response_code })}
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-hairline pt-4">
              <Button type="button" variant="ghost" size="sm" onClick={closeForm}>
                {t("activity.testDelivery.cancel")}
              </Button>
              <Button type="submit" size="sm" disabled={!destination.trim() || test.isPending}>
                {test.isPending ? t("activity.testDelivery.sending") : t("activity.testDelivery.send")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
