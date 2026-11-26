# WebMonitor Design System

This document describes the interface implemented in `web/src`. It is a working specification for product UI, not a visual reference for another site.

The interface is an operator's editorial desk: warm paper, deep-green actions, quiet rules, serif page titles, sans-serif controls, and monospace evidence. Use surface steps and separators to establish hierarchy. Dark surfaces contain machine output and before/after evidence; they are not a separate dark theme.

## Source of truth

- Theme tokens and global styles: `web/src/app/globals.css`
- Shared controls: `web/src/components/ui/`
- Shared page composition: `web/src/components/{page-header,workspace-shell,empty-state,list-pagination}.tsx`
- Tailwind CSS 4 is configured through `@theme inline` in `globals.css`; there is no separate Tailwind configuration file.
- Lucide is the icon set. Use existing shared primitives before composing a local variant.

Email templates have their own user-editable colors and typography. Do not apply those settings to the web application.

## 1. Color

### Surfaces and text

| Token | Value | Use |
|---|---|---|
| `canvas` / `background` | `#fbfaf7` | Page floor, inputs, popovers, selected navigation rows |
| `surface-soft` / `muted` | `#f5f3ee` | Sidebar, quiet bands, authentication aside |
| `surface-card` / `card` | `#efede7` | User messages, selected filters and options |
| `surface-strong` / `secondary` | `#e8e5dd` | Secondary buttons, inline code, hover fills |
| `ink` / `foreground` | `#1c201e` | Titles, primary labels, current values |
| `body` | `#3f4541` | Running text |
| `muted-foreground` | `#656b65` | Descriptions, field labels, secondary copy |
| `muted-soft` | `#858a82` | Timestamps, metadata, placeholders; see contrast limitation below |
| `hairline` | `#e2dfd7` | Default borders and record separators |
| `hairline-soft` | `#eae7e0` | Quiet internal dividers |
| `field-line` / `input` | `#d8d5cc` | Form-control borders |

`border` defaults to `hairline`; `popover` uses `canvas`; `ring` uses `primary`. Prefer these semantic aliases in components rather than introducing literal colors.

### Actions and status

| Token | Value | Use |
|---|---|---|
| `primary` | `#285f49` | Primary actions, brand mark, active indicators, focus color |
| `primary-active` | `#1d4937` | Primary hover and inline links |
| `on-primary` | `#ffffff` | Text and icons on primary actions |
| `success` | `#4f7f5f` | Success borders, tints, live indicators |
| `success-ink` | `#285f49` | Success text and additions |
| `warning` | `#b18439` | Warning borders and tints |
| `warning-ink` | `#79581f` | Warning text |
| `error` / `destructive` | `#b54339` | Errors, destructive actions, failed or removed states |

Use one primary action in a local action group. Status must also have text or an icon; color alone is not the message. Badges use a semantic border at low alpha and a quiet background tint, not a saturated fill.

### Machine-output surfaces

| Token | Value | Use |
|---|---|---|
| `surface-dark` | `#1c2421` | Change records, raw JSON, code and mail bodies |
| `surface-dark-elevated` | `#27312d` | Nested output rows and blocks |
| `surface-dark-line` | `#35403b` | Dark output borders |
| `on-dark` | `#f7f6f1` | Primary output text |
| `on-dark-soft` | `#aab3ac` | Secondary output text |

Do not place ordinary forms on dark output surfaces or use them as decorative section backgrounds.

## 2. Typography

No fonts are downloaded. The stacks use locally installed and platform fonts:

- Display: `"Iowan Old Style", "Palatino Linotype", Palatino, Charter, Georgia, "Songti SC", "Noto Serif SC", "Source Han Serif SC", serif`
- UI: `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`
- Code: `"JetBrains Mono", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace`

| Style | Specification | Use |
|---|---|---|
| Body | UI, 15px, 400, line-height 1.6 | Default text |
| `display-xl` | Display, `clamp(40px, 4.2vw, 56px)`, 400, 1.05, `-0.025em` | Public hero |
| `display-md` | Display, `clamp(28px, 3.2vw, 36px)`, 400, 1.15, `-0.02em` | Public sections, authentication, not-found page |
| `display-sm` | Display, 28px, 400, 1.2, `-0.015em` | Small display moments |
| `page-title` | Display, 28px, 400, 1.2, `-0.015em` | Workspace `PageHeader` |
| Dialog title | Display, 26px, 400, 1.15, `-0.02em` | Modal heading |
| `section-title` / `t-title` | UI, 18px, 500, 1.4 | Panel and section headings |
| `t-body-sm` | UI, 14px, 1.55 | Secondary body |
| `meta` / `t-caption` | UI, 13px | Metadata and captions |
| `label-line` / `eyebrow` | UI, 12px, 500 | Field groups and section labels |
| Form label | UI, 13px, 500 | Associated control label |
| Badge | UI, 11px, 500, 16px line-height | Compact status |
| Button | UI, 14px, 500; small 13px | Actions |
| Code window | Code, 13px, 1.7 | Evidence and machine output |

Only `h1` uses the display face by default. Keep `h2`–`h4` in UI sans unless a component explicitly applies a display class. Display headings stay at weight 400; controls and panel headings use 500 where emphasis is needed.

Use `.num` or the code stack with tabular numerals for timestamps, counts, versions, intervals, selectors, URLs, and specifications. Assistant Markdown has its own established hierarchy; do not turn every panel heading into a serif title.

## 3. Spacing and layout

Use Tailwind's 4px spacing base directly. Do not add a parallel spacing-token system.

- Control gaps: 8px, 12px, or 16px.
- Content groups: 24px, 32px, 40px, 48px, or 64px.
- `PageBody`: maximum width 80rem; horizontal padding 24px, 32px at `sm`, 40px at `lg`; vertical padding 32px, then 40px at `sm`.
- `PageHeader`: bottom hairline, 24px bottom padding, 32px bottom margin, 20px gap between title and actions.
- Public container: maximum width 76rem; public major sections use 96px vertical padding, 112px at `sm`.
- Chat column: maximum width 46rem with 24px side padding.
- Authentication form: maximum width 22rem.

Use default Tailwind breakpoints: `sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px. Collapse multi-column facts and rails before compressing their content. Tables and code may scroll horizontally; primary values and actions must not be clipped.

## 4. Shape, elevation, and motion

| Treatment | Value | Use |
|---|---|---|
| `rounded-sm` | 6px | Small local elements |
| `rounded-md` | 8px | Inputs, selects, compact controls |
| `rounded-lg` | 12px | Buttons, navigation rows, list panels, composer |
| `rounded-xl` | 16px | `.surface`, dialogs, dark artifacts |
| `rounded-full` | Pill or circle | Badges, avatar, compact floating actions |
| `shadow-soft` | `0 20px 48px rgba(28, 32, 30, 0.10)` | Dialogs and the authentication artifact |
| `shadow-pop` | `0 8px 24px rgba(28, 32, 30, 0.10)` | Selects and action-menu popovers |

Ordinary records are flat and separated by hairlines. Avoid nested cards and default drop shadows. Use one bordered `.surface` for a featured artifact, not for every row.

Motion uses `cubic-bezier(0.22, 1, 0.36, 1)`. Hover and press transitions are 150ms; the mobile sidebar is 200ms. Press feedback is `scale(0.98)`. Keep motion functional and restrained. Honor `prefers-reduced-motion`; pending indicators still need a non-motion text state.

Lucide icons normally use a 1.5 stroke and 14–20px boxes. Icon-only actions require an accessible localized name.

## 5. Controls

### Buttons

Use `components/ui/button.tsx`:

- `default`: primary green with white text; use for the main action.
- `outline`: field border and canvas background; use for a parallel secondary action.
- `ghost`: quiet row and toolbar actions.
- `secondary`: surface-strong fill for neutral emphasis.
- `destructive`: error fill; pair with explicit confirmation when data is affected.
- `link`: inline navigation or low-emphasis text action.

Sizes are default 40px high with 20px horizontal padding, small 32px/12px, large 44px/24px, and icon 36×36px. Disabled buttons use 45% opacity and do not accept pointer input. Buttons use a 3px primary/20% focus ring and a subtle press scale.

### Inputs, textareas, and selects

- Shared `Input`: 40px high, 8px radius, 14px horizontal padding, 14px text, canvas background, field-line border.
- Focus: primary border and 3px primary/15% ring.
- Associate every input with a `Label`; placeholder text is an example, not a label.
- Textareas follow the same visual language. Raw JSON, recipient lists, and specifications may use the code stack.
- Custom `Select`: 32px small or 40px medium trigger; popover uses 12px radius, `shadow-pop`, a 256px maximum height, and a 352px maximum width.
- Native checkboxes are 16px with `accent-color: primary`.
- Preserve keyboard behavior and focus return when extending the custom select.

### Badges, navigation, and feedback

- Badges are compact pills with an 11px label, semantic hairline/tint, and a text status.
- Workspace navigation rows are 36px high with a 12px radius and 12px horizontal padding. Current navigation uses canvas, hairline, and `aria-current="page"`.
- Toggle-style filters expose `aria-pressed` and use surface-card plus stronger text for selection.
- Empty states use a top rule, title, and muted explanation; do not introduce dashed placeholder cards.
- Loading uses quiet text or an activity indicator. Errors stay near their cause and use `role="alert"` when they need announcement.
- List pagination is a loaded-count summary plus “load more,” not a numbered page control.
- Native `details/summary` is the default for configuration and tool-detail disclosure.

### Dialogs

Use the shared Radix dialog. Content is centered on canvas with a 16px radius, hairline, 24px padding, `shadow-soft`, a 90dvh maximum height, and a default 672px maximum width. Keep a labelled title and close action. Use narrower widths for focused tasks rather than stretching a small form.

## 6. Page patterns

### Public entry

Use the wordmark, language switch, and workspace link in a restrained header. The hero pairs concise copy with a dark before/after change record at `xl`. Numbered steps and feature descriptions use ruled rows or a two-column ruled grid. The change record is the product artifact; avoid decorative feature-card grids.

### Authentication

Use a 64px bordered header and a 352px form column. At `lg`, add the soft-surface aside with the dark sample change record. Invitation warnings and submission errors remain inline with the form.

### Workspace shell

The workspace fills `100dvh` and scrolls within its regions. The 280px sidebar has a soft surface, 64px brand header, and 64px account footer. Below `md`, it is an off-canvas drawer with backdrop, focus containment, Escape dismissal, and focus restoration. The 336px chat context rail appears only at `xl`.

### Conversation

Assistant prose is full width without an avatar bubble. User messages are right-aligned surface-card bubbles capped at 85% width. Tool calls use a hairline left rail, semantic status dots, and expandable code windows. The composer is one bordered composite with a focus-within ring, an auto-growing textarea capped at 200px, and a labelled send/stop action. Drafts and approval actions stay in the conversation flow.

### Operational pages

Use `PageBody` and `PageHeader` for monitors, events, snapshots, notifications, templates, tokens, and members.

- Facts form a ruled strip, not a grid of metric cards.
- Lists use `border-t`, `divide-y`, and 12–16px row padding.
- Monitor details split into main content and a 384px baseline column at `lg`.
- Notifications, tokens, and members use wider two-column layouts only at `xl`.
- Field values and changes read as ledgers: labels and values align, numbers are tabular, old values are struck through, and additions/removals have explicit text.
- Keep the primary object and its next action visible before secondary metadata.

## 7. Accessibility

### Existing requirements

- Preserve the global `:focus-visible` treatment: 2px solid primary outline with 2px offset, unless a control supplies an equivalent visible focus style.
- Keep the document `lang` synchronized with the active English or Chinese locale.
- Use semantic headings, associated form labels, localized names for icon-only actions, and text in addition to status color.
- Preserve `aria-current`, `aria-pressed`, alert/status roles, dialog semantics, keyboard select behavior, and mobile-navigation focus management.
- Respect reduced motion: remove infinite pulse/spinner animations and keep text status equivalents. Preserve the workspace skip link and polite run-start/completion/failure/cancellation announcements; do not stream tokens into live regions.
- Check normal-text contrast at 4.5:1 and non-text control/focus contrast at 3:1 when introducing or changing colors.

### Known limitations to carry into review

These are current audit items, not accepted design goals:

- `muted-soft` on `canvas` is approximately 3.38:1 and is used for small metadata and placeholders. Do not expand it to essential normal-size text; strengthen the treatment when auditing those uses.
- Some low-alpha control focus rings need stronger contrast, particularly on primary-green buttons.
- Small, icon, and compact row actions include targets below 44×44px. Review WCAG 2.2 target size and spacing before adding more compact actions.
- The monitor action menu and token client selector need a keyboard/state-semantics review before being used as patterns for new controls.

New work must not copy these gaps silently. Prefer the established labelled, keyboard-operable patterns and verify the affected flow with keyboard and reduced-motion settings.
