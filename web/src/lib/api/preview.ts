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

const ruleSchema = z.object({
  type: z.string(),
  field: z.string().optional(),
  operator: z.string().optional(),
  value: z.union([z.number(), z.string()]).optional(),
  keyword: z.string().optional(),
  watch_fields: z.array(z.string()).optional(),
});

export const draftSpecSchema = z.object({
  name: z.string().optional(),
  url: z.string().optional(),
  collection_mode: z.string().optional(),
  fields: z.array(
    z.object({
      name: z.string(),
      type: z.string(),
      semantic: z.string().optional(),
      selector: z.string().optional(),
    }),
  ),
  change_rules: z
    .object({ mode: z.string().optional(), rules: z.array(ruleSchema) })
    .optional(),
  schedule: z.object({ interval_seconds: z.number(), timezone: z.string().optional() }).optional(),
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
