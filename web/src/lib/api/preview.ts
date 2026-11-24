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
  recipient_count: z.number().int().nonnegative(),
  recipient_sources: z.array(recipientSourceSchema),
  warnings: z.array(z.string()),
  created_at: z.string(),
  expires_at: z.string(),
});

const scalarSchema = z.union([z.number(), z.string()]);
const ruleBase = { field: z.string().min(1) };
const ruleSchema = z.discriminatedUnion("type", [
  z.strictObject({ ...ruleBase, type: z.literal("text_changed") }),
  z.strictObject({ ...ruleBase, type: z.literal("value_changed") }),
  z.strictObject({
    ...ruleBase,
    type: z.literal("regex_match"),
    pattern: z.string().min(1).max(1000),
  }),
  z.strictObject({ ...ruleBase, type: z.literal("keyword_present"), keyword: z.string().min(1) }),
  z.strictObject({ ...ruleBase, type: z.literal("keyword_absent"), keyword: z.string().min(1) }),
  z.strictObject({
    ...ruleBase,
    type: z.literal("number_absolute_change"),
    operator: z.enum(["increase_gte", "decrease_gte", "change_gte"]),
    value: scalarSchema,
  }),
  z.strictObject({
    ...ruleBase,
    type: z.literal("number_percent_change"),
    operator: z.enum(["increase_gte", "decrease_gte", "change_gte"]),
    value: scalarSchema,
  }),
  z.strictObject({
    ...ruleBase,
    type: z.literal("threshold"),
    operator: z.enum(["gt", "gte", "lt", "lte", "eq"]),
    value: scalarSchema,
  }),
  z.strictObject({ ...ruleBase, type: z.literal("list_added") }),
  z.strictObject({ ...ruleBase, type: z.literal("list_removed") }),
  z.strictObject({
    ...ruleBase,
    type: z.literal("list_updated"),
    watch_fields: z.array(z.string().min(1)).min(1),
  }),
]);

const normalizationSchema = z.strictObject({
  trim: z.boolean().default(true),
  collapse_whitespace: z.boolean().default(false),
  decimal_separator: z.enum([".", ","]).nullish(),
  thousands_separator: z.enum([".", ",", " ", "'"]).nullish(),
  currency: z.string().regex(/^[A-Z]{3}$/).nullish(),
  date_format: z.string().min(1).max(100).nullish(),
  timezone: z.string().min(1).nullish(),
  true_values: z.array(z.string()).default([]),
  false_values: z.array(z.string()).default([]),
});

const fieldShape = {
  name: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,63}$/),
  type: z.enum(["text", "number", "money", "date", "boolean", "url", "list"]),
  semantic: z.string().min(1).max(500),
  selector: z.string().min(1).max(1000).nullish(),
  path: z.string().min(1).max(500).nullish(),
  attribute: z.string().regex(/^[A-Za-z_][A-Za-z0-9_:-]*$/).nullish(),
  required: z.boolean().default(true),
  allow_empty: z.boolean().default(false),
  normalize: normalizationSchema.default({ trim: true, collapse_whitespace: false, true_values: [], false_values: [] }),
  min_items: z.number().int().nonnegative().nullish(),
  max_items: z.number().int().nonnegative().nullish(),
};

const itemFieldSchema = z.strictObject({
  ...fieldShape,
  // Nested list fields are invalid; scalar item fields still serialize this as null.
  item_fields: z.null().optional(),
});
const fieldSchema = z.strictObject({
  ...fieldShape,
  // The backend rejects nested lists, so one level covers every valid spec.
  item_fields: z.array(itemFieldSchema).nullish(),
});

const browserStepSchema = z.discriminatedUnion("type", [
  z.strictObject({
    type: z.literal("wait_for_selector"),
    selector: z.string().min(1),
    timeout_ms: z.number().int().positive().max(10000).default(10000),
  }),
  z.strictObject({
    type: z.literal("scroll"),
    max_steps: z.number().int().min(1).max(5),
  }),
  z.strictObject({
    type: z.literal("click_next"),
    selector: z.string().min(1),
    max_pages: z.number().int().min(1).max(3),
  }),
]);

const requestSchema = z.strictObject({
  method: z.enum(["GET", "POST"]).default("GET"),
  url: z.string().min(1).max(4096),
  headers: z.record(z.string(), z.string()).default({}),
  body: z.unknown().nullish(),
});

const assertionSchema = z.discriminatedUnion("type", [
  z.strictObject({
    type: z.literal("json_equals"),
    path: z.string().min(1).max(500),
    equals: z.union([z.string(), z.number(), z.boolean(), z.null()]),
  }),
  z.strictObject({
    type: z.literal("json_present"),
    path: z.string().min(1).max(500),
  }),
]);

const paginationBaseSchema = z.strictObject({
  location: z.enum(["query", "body"]).default("query"),
  size_param: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,31}$/).nullish(),
  size: z.number().int().min(1).max(1000).nullish(),
  total_path: z.string().min(1).max(500).nullish(),
  stop: z.enum(["empty", "total_reached"]).default("empty"),
  max_pages: z.number().int().min(1).max(5).default(3),
  max_items: z.number().int().min(1).max(2000).default(500),
});

const paginationSchema = z.discriminatedUnion("kind", [
  paginationBaseSchema.extend({
    kind: z.literal("page").default("page"),
    page_param: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,31}$/).default("page"),
    start_page: z.number().int().min(1).max(10000).default(1),
  }),
  paginationBaseSchema.extend({
    kind: z.literal("cursor"),
    cursor_param: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,31}$/).default("cursor"),
    start_cursor: z.union([z.string(), z.number()]).nullish(),
    next_cursor_path: z.string().min(1).max(500),
  }),
  paginationBaseSchema.extend({
    kind: z.literal("offset"),
    offset_param: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,31}$/).default("offset"),
    start_offset: z.number().int().min(0).max(1000000).default(0),
  }),
]);

const sourceSchema = z.strictObject({
  kind: z.literal("json").default("json"),
  steps: z.array(z.strictObject({
    id: z.string().regex(/^[a-z][a-z0-9_]{0,31}$/),
    request: requestSchema,
  })).min(1).max(3),
  assertions: z.array(assertionSchema).max(8).default([]),
  pagination: paginationSchema.nullish(),
});

/** The collection contract only; recipients, cadence and template are settings. */
export const monitorSpecSchema = z.strictObject({
  name: z.string().min(1).max(200),
  url: z.string().min(1).max(4096),
  collection_mode: z.enum(["http", "browser"]),
  fields: z.array(fieldSchema).min(1),
  business_key: z.strictObject({
    field: z.string(),
    item_fields: z.array(z.string()).min(1),
  }).nullish(),
  change_rules: z.strictObject({
    mode: z.enum(["all", "any"]),
    rules: z.array(ruleSchema).min(1),
    consecutive_hits: z.number().int().min(1).max(10).default(1),
  }),
  coverage: z.strictObject({
    scope: z.enum(["full", "bounded"]),
    description: z.string().min(1).max(2000),
  }),
  browser_steps: z.array(browserStepSchema).default([]),
  source: sourceSchema.nullish(),
});

/** User-owned delivery settings; a draft may still be empty here. */
const clockTimeSchema = z.string().regex(/^(?:[01]\d|2[0-3]):[0-5]\d$/);
const quietHoursSchema = z.strictObject({
  start: clockTimeSchema,
  end: clockTimeSchema,
}).refine((value) => value.start !== value.end);

export const deliverySettingsSchema = z.object({
  channel: z.enum(["email", "webhook", "both"]).default("email"),
  event_channels: z.partialRecord(z.enum(["content_changed", "list_changed", "run_failed", "recovered"]),
    z.enum(["email", "webhook"])).default({}),
  notification_group_ids: z.array(z.string()),
  webhook_url: z.string().nullish(),
  schedule: z
    .strictObject({
      interval_seconds: z.number().int().min(60).max(86400),
      timezone: z.string().min(1),
    })
    .nullish(),
  email_template_id: z.string().nullish(),
  notification_cooldown_seconds: z.number().int().nonnegative().max(2_147_483_647).default(0),
  quiet_hours: quietHoursSchema.nullish(),
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
