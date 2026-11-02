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

const previewSourceSchema = z.object({
  kind: z.string(),
  steps: z.array(
    z.object({
      id: z.string(),
      method: z.string(),
      url: z.string(),
      status: z.number(),
      pages: z.number().optional(),
    }),
  ),
  assertions: z.array(
    z.object({ type: z.string(), path: z.string().optional(), passed: z.boolean() }),
  ),
  pages: z.number(),
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
  source: previewSourceSchema.nullish(),
});

const ruleSchema = z.object({
  type: z.string(),
  field: z.string().optional(),
  operator: z.string().optional(),
  value: z.union([z.number(), z.string()]).optional(),
  keyword: z.string().optional(),
  watch_fields: z.array(z.string()).optional(),
});

const normalizationSchema = z.object({
  trim: z.boolean().optional(),
  collapse_whitespace: z.boolean().optional(),
  decimal_separator: z.string().nullish(),
  thousands_separator: z.string().nullish(),
  currency: z.string().nullish(),
  date_format: z.string().nullish(),
  timezone: z.string().nullish(),
  true_values: z.array(z.string()).optional(),
  false_values: z.array(z.string()).optional(),
});

const fieldShape = {
  name: z.string(),
  type: z.string(),
  semantic: z.string().optional(),
  selector: z.string().nullish(),
  path: z.string().nullish(),
  attribute: z.string().nullish(),
  required: z.boolean().optional(),
  normalize: normalizationSchema.optional(),
  min_items: z.number().nullish(),
  max_items: z.number().nullish(),
};

const fieldSchema = z.object({
  ...fieldShape,
  // The backend rejects nested lists, so one level covers every valid spec.
  item_fields: z.array(z.object(fieldShape)).nullish(),
});

const browserStepSchema = z.object({
  type: z.string(),
  selector: z.string().optional(),
  timeout_ms: z.number().optional(),
  max_steps: z.number().optional(),
  max_pages: z.number().optional(),
});

const requestSchema = z.object({
  method: z.string().optional(),
  url: z.string(),
  headers: z.record(z.string(), z.string()).optional(),
  body: z.unknown().optional(),
});

const assertionSchema = z.object({
  type: z.string(),
  path: z.string().optional(),
  equals: z.union([z.string(), z.number(), z.boolean(), z.null()]).optional(),
});

const pagePaginationSchema = z.object({
  kind: z.string().optional(),
  page_param: z.string().optional(),
  start_page: z.number().optional(),
  size_param: z.string().nullish(),
  size: z.number().nullish(),
  total_path: z.string().nullish(),
  stop: z.string().optional(),
  max_pages: z.number().optional(),
  max_items: z.number().optional(),
});

const sourceSchema = z.object({
  kind: z.string().optional(),
  steps: z.array(z.object({ id: z.string(), request: requestSchema })),
  assertions: z.array(assertionSchema).optional(),
  pagination: pagePaginationSchema.nullish(),
});

export const draftSpecSchema = z.object({
  name: z.string().optional(),
  url: z.string().optional(),
  collection_mode: z.string().optional(),
  fields: z.array(fieldSchema),
  business_key: z
    .object({ field: z.string(), item_fields: z.array(z.string()) })
    .nullish(),
  change_rules: z
    .object({ mode: z.string().optional(), rules: z.array(ruleSchema) })
    .optional(),
  schedule: z.object({ interval_seconds: z.number(), timezone: z.string().optional() }).optional(),
  notification_group_ids: z.array(z.string()).optional(),
  coverage: z
    .object({ scope: z.string().optional(), description: z.string().optional() })
    .optional(),
  browser_steps: z.array(browserStepSchema).optional(),
  source: sourceSchema.nullish(),
});

export type DraftPreview = z.infer<typeof draftPreviewSchema>;
export type DraftSpecView = z.infer<typeof draftSpecSchema>;
export type SpecField = z.infer<typeof fieldSchema>;
export type SpecRule = z.infer<typeof ruleSchema>;
export type BrowserStep = z.infer<typeof browserStepSchema>;

export function parsePreview(value: unknown): DraftPreview | null {
  const parsed = draftPreviewSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parseSpec(value: unknown): DraftSpecView | null {
  const parsed = draftSpecSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}
