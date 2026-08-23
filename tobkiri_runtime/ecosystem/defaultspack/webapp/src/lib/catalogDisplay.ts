export type CatalogReferenceKind =
  | "tool"
  | "skill"
  | "agent"
  | "file"
  | "memory"
  | "conversation";

export type CatalogDisplayMetadata = {
  id: string;
  kind: CatalogReferenceKind;
  label: string;
  description?: string;
  icon: string;
  image?: string;
  risk?: string;
  status?: string;
  aliases: string[];
};

export type CatalogDisplayInput = Omit<CatalogDisplayMetadata, "aliases" | "icon"> & {
  aliases?: string[];
  icon?: string;
};

const DEFAULT_REFERENCE_ICONS: Record<CatalogReferenceKind, string> = {
  tool: "wrench",
  skill: "brain",
  agent: "bot",
  file: "file",
  memory: "database",
  conversation: "message",
};

function cleanOptional(value: unknown): string | undefined {
  const clean = String(value ?? "").trim();
  return clean || undefined;
}

/** Resolve display metadata once for composer, sidebar, widget, and panel surfaces. */
export function resolveCatalogDisplayMetadata(
  input: CatalogDisplayInput,
): CatalogDisplayMetadata {
  const id = String(input.id ?? "").trim();
  const label = cleanOptional(input.label) ?? id;
  return {
    id,
    kind: input.kind,
    label,
    icon: cleanOptional(input.icon) ?? DEFAULT_REFERENCE_ICONS[input.kind],
    aliases: [...new Set(
      (input.aliases ?? []).map((alias) => String(alias ?? "").trim()).filter(Boolean),
    )],
    ...(cleanOptional(input.description)
      ? { description: cleanOptional(input.description) }
      : {}),
    ...(cleanOptional(input.image) ? { image: cleanOptional(input.image) } : {}),
    ...(cleanOptional(input.risk) ? { risk: cleanOptional(input.risk) } : {}),
    ...(cleanOptional(input.status) ? { status: cleanOptional(input.status) } : {}),
  };
}

/** Stable aliases used for typed lookup and trusted clipboard restoration. */
export function catalogDisplayAliases(item: CatalogDisplayMetadata): string[] {
  return [...new Set([
    item.id,
    item.id.split("/").pop() ?? "",
    item.label,
    item.label.replace(/\s+/g, "_"),
    ...item.aliases,
    ...item.aliases.map((alias) => alias.replace(/\s+/g, "_")),
  ].map((value) => value.trim()).filter(Boolean))];
}

/** Merge reference sources without letting later duplicate identities shadow authority. */
export function mergeCatalogDisplayMetadata(
  ...sources: CatalogDisplayMetadata[][]
): CatalogDisplayMetadata[] {
  const merged = new Map<string, CatalogDisplayMetadata>();
  for (const item of sources.flat()) {
    const key = `${item.kind}:${item.id}`;
    if (!item.id || merged.has(key)) continue;
    merged.set(key, resolveCatalogDisplayMetadata(item));
  }
  return [...merged.values()];
}

export function filterCatalogDisplayMetadata(
  items: CatalogDisplayMetadata[],
  query: string,
  limit = 40,
): CatalogDisplayMetadata[] {
  const normalizedQuery = query.trim().toLowerCase();
  const matches = normalizedQuery
    ? items.filter((item) => [
        item.id,
        item.label,
        item.description,
        item.kind,
        ...item.aliases,
      ].filter(Boolean).join(" ").toLowerCase().includes(normalizedQuery))
    : items;
  return matches.slice(0, Math.max(0, limit));
}
