export type SelectOption = { value: string; label: string };

/** An unloaded page is not evidence that a stored notification group is gone. */
export function missingGroupIds(
  selectedIds: string[],
  loadedIds: string[],
  hasNextPage: boolean,
): string[] {
  if (hasNextPage) return [];
  const loaded = new Set(loadedIds);
  return selectedIds.filter((id) => !loaded.has(id));
}

/** Keep the exact selected value and its frozen name visible outside loaded pages. */
export function withSelectedTemplate(
  options: SelectOption[],
  selectedId: string | null,
  selectedName: string | null,
  fallbackLabel: string,
): SelectOption[] {
  if (!selectedId || options.some((option) => option.value === selectedId)) return options;
  return [
    ...options,
    { value: selectedId, label: selectedName?.trim() || fallbackLabel },
  ];
}

/** The monitor stores the approved template's name with its frozen definition. */
export function frozenTemplateName(value: unknown): string | null {
  if (!value || typeof value !== "object" || !("name" in value)) return null;
  const name = value.name;
  return typeof name === "string" && name.trim() ? name : null;
}
