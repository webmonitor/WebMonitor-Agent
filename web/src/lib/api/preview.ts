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

const recipientSourceSchema = z.object({
  email: z.string(),
  group_ids: z.array(z.string()),
});

/** What a real collection produced for the saved collection contract. */
export const extractionPreviewSchema = z.object({
  preview_id: z.string(),
  spec_revision: z.number(),
  spec_hash: z.string(),
  extracted_data: z.record(z.string(), z.unknown()),
  coverage: z.object({ scope: z.string().optional(), description: z.string().optional() }),
  final_url: z.string().nullish(),
  evidence_refs: z.array(evidenceRefSchema),
  rule_simulation: z.record(z.string(), z.unknown()),
  source: previewSourceSchema.nullish(),
  warnings: z.array(z.string()),
  created_at: z.string(),
  expires_at: z.string(),
});

/** What the mail will look like for the current settings and template. */
export const deliveryPreviewSchema = z.object({
  preview_id: z.string(),
  settings_revision: z.number(),
  settings_hash: z.string(),
  channel: z.string().default("email"),
  webhook_url: z.string().nullish(),
  webhook_body: z.record(z.string(), z.unknown()).nullish(),
  template_id: z.string().nullish(),
  template_name: z.string().nullish(),
  template_hash: z.string(),
  rendered_emails: z.array(renderedEmailSchema),
  recipients: z.array(z.string()),
  recipient_sources: z.array(recipientSourceSchema),
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
  allow_empty: z.boolean().optional(),
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

/** The collection contract only; recipients, cadence and template are settings. */
export const monitorSpecSchema = z.object({
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
  coverage: z
    .object({ scope: z.string().optional(), description: z.string().optional() })
    .optional(),
  browser_steps: z.array(browserStepSchema).optional(),
  source: sourceSchema.nullish(),
});

/** User-owned delivery settings; a draft may still be empty here. */
export const deliverySettingsSchema = z.object({
  channel: z.enum(["email", "webhook"]).default("email"),
  notification_group_ids: z.array(z.string()),
  webhook_url: z.string().nullish(),
  schedule: z
    .object({ interval_seconds: z.number(), timezone: z.string() })
    .nullish(),
  email_template_id: z.string().nullish(),
});

const templateBlockSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("text"), text: z.string() }),
  z.object({ type: z.literal("summary") }),
  z.object({
    type: z.literal("field"),
    field: z.string(),
    show: z.enum(["current", "before", "both"]).optional(),
    emphasis: z.boolean().optional(),
    label: z.string().nullish(),
  }),
  z.object({ type: z.literal("list_changes"), field: z.string(), limit: z.number().optional() }),
  z.object({ type: z.literal("all_fields"), fields: z.array(z.string()).nullish() }),
  z.object({ type: z.literal("event_time") }),
  z.object({ type: z.literal("monitor_link") }),
  z.object({ type: z.literal("evidence_link") }),
  z.object({ type: z.literal("divider") }),
]);

/** The look of a design: bounded tokens the server turns into the mail CSS. */
export const templateStyleSchema = z.object({
  page_background: z.string().optional(),
  surface: z.string().optional(),
  text: z.string().optional(),
  muted: z.string().optional(),
  accent: z.string().optional(),
  font: z.enum(["sans", "serif", "mono"]).optional(),
  heading_scale: z.enum(["compact", "regular", "large"]).optional(),
  density: z.enum(["tight", "regular", "roomy"]).optional(),
  radius: z.number().optional(),
  border: z.boolean().optional(),
  uppercase_labels: z.boolean().optional(),
});

/** A stored mail design; the backend renders it, this only describes it. */
export const emailTemplateConfigSchema = z.object({
  version: z.literal(1).optional(),
  style: templateStyleSchema.optional(),
  subject: z.string(),
  intros: z.record(z.string(), z.string()).optional(),
  blocks: z.array(templateBlockSchema).optional(),
});

export type ExtractionPreview = z.infer<typeof extractionPreviewSchema>;
export type DeliveryPreview = z.infer<typeof deliveryPreviewSchema>;
export type MonitorSpecView = z.infer<typeof monitorSpecSchema>;
export type DeliverySettingsView = z.infer<typeof deliverySettingsSchema>;
export type EmailTemplateConfigView = z.infer<typeof emailTemplateConfigSchema>;
export type TemplateStyleView = z.infer<typeof templateStyleSchema>;
export type TemplateBlockView = z.infer<typeof templateBlockSchema>;
export type RenderedEmailView = z.infer<typeof renderedEmailSchema>;
export type SpecField = z.infer<typeof fieldSchema>;
export type SpecRule = z.infer<typeof ruleSchema>;
export type BrowserStep = z.infer<typeof browserStepSchema>;

export function parseExtractionPreview(value: unknown): ExtractionPreview | null {
  const parsed = extractionPreviewSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parseDeliveryPreview(value: unknown): DeliveryPreview | null {
  const parsed = deliveryPreviewSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parseSpec(value: unknown): MonitorSpecView | null {
  const parsed = monitorSpecSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parseSettings(value: unknown): DeliverySettingsView | null {
  const parsed = deliverySettingsSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

export function parseTemplateConfig(value: unknown): EmailTemplateConfigView | null {
  const parsed = emailTemplateConfigSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}
