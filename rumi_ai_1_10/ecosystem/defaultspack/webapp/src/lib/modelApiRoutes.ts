export type ParsedModelApiRouteLine =
  | { kind: "route"; model: string; apis: string[]; raw: string }
  | { kind: "raw"; raw: string };

export function parseModelApiRouteLines(value: unknown): ParsedModelApiRouteLine[] {
  return String(value ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.startsWith("#")) return { kind: "raw", raw: line };
      const match = line.match(/^(.+?):\s*(.+)$/);
      if (!match) return { kind: "raw", raw: line };
      const model = match[1]?.trim() ?? "";
      const apis = (match[2] ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      return model && apis.length ? { kind: "route", model, apis, raw: line } : { kind: "raw", raw: line };
    });
}

export function selectedApisForModel(value: unknown, model: string): string[] {
  const target = String(model ?? "").trim();
  if (!target) return [];
  const route = parseModelApiRouteLines(value).find((line) => line.kind === "route" && line.model === target);
  return route?.kind === "route" ? [...route.apis] : [];
}

export function updateModelApiRouteText(value: unknown, model: string, apis: string[]): string {
  const target = String(model ?? "").trim();
  if (!target) return String(value ?? "");
  const cleanedApis = apis.map((api) => String(api ?? "").trim()).filter(Boolean);
  const lines = parseModelApiRouteLines(value);
  let replaced = false;
  const nextLines: string[] = [];
  for (const line of lines) {
    if (line.kind !== "route" || line.model !== target) {
      nextLines.push(line.raw);
      continue;
    }
    replaced = true;
    if (cleanedApis.length > 0) {
      nextLines.push(`${target}: ${cleanedApis.join(", ")}`);
    }
  }
  if (!replaced && cleanedApis.length > 0) {
    nextLines.push(`${target}: ${cleanedApis.join(", ")}`);
  }
  return nextLines.join("\n") + (nextLines.length ? "\n" : "");
}

export function toggleModelApiRoute(value: unknown, model: string, apiRef: string): string {
  const selectedApis = selectedApisForModel(value, model);
  const cleanedRef = String(apiRef ?? "").trim();
  if (!cleanedRef) return updateModelApiRouteText(value, model, selectedApis);
  const nextApis = selectedApis.includes(cleanedRef)
    ? selectedApis.filter((item) => item !== cleanedRef)
    : [...selectedApis, cleanedRef];
  return updateModelApiRouteText(value, model, nextApis);
}
