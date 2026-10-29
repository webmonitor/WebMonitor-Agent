import { z } from "zod";

export const evidenceRefSchema = z.object({
  kind: z.string(),
  bucket: z.string(),
  object_key: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  sha256: z.string(),
});

export const renderedEmailSchema = z.object({
  event_type: z.string(),
  subject: z.string(),
  html: z.string(),
  text: z.string(),
  preview_html: z.string().optional(),
});

export const draftPreviewSchema = z.object({
  revision: z.number(),
  spec_hash: z.string(),
  extracted_data: z.record(z.string(), z.unknown()),
  coverage: z.object({ scope: z.string().optional(), description: z.string().optional() }),
  final_url: z.string().nullish(),
  evidence_refs: z.array(evidenceRefSchema),
  rule_simulation: z.record(z.string(), z.unknown()),
  rendered_emails: z.array(renderedEmailSchema),
  recipients: z.array(z.string()),
  warnings: z.array(z.string()),
  created_at: z.string(),
  expires_at: z.string(),
});

export const draftSpecSchema = z.object({
  fields: z.array(z.object({ name: z.string(), type: z.string(), semantic: z.string().optional() })),
});

export type DraftPreview = z.infer<typeof draftPreviewSchema>;
export type DraftSpecView = z.infer<typeof draftSpecSchema>;

export function parsePreview(value: unknown): DraftPreview | null {
  const parsed = draftPreviewSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parseSpec(value: unknown): DraftSpecView | null {
  const parsed = draftSpecSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}
