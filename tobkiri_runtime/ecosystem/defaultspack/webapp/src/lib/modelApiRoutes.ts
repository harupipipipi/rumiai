export type ParsedModelApiRouteLine =
  | { kind: "route"; model: string; apis: string[]; raw: string }
  | { kind: "raw"; raw: string };

export type StructuredModelApiRoute = {
  model: string;
  apis: string[];
  raw: Record<string, unknown>;
};

function parseJsonish(value: unknown): unknown {
  if (typeof value !== "string") return value;
  const text = value.trim();
  if (!text || (!text.startsWith("{") && !text.startsWith("["))) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function apiRefsFromRoute(route: Record<string, unknown>): string[] {
  const rawApis = route.apis ?? route.api_ids ?? route.apiKeys ?? route.keys ?? route.route;
  if (Array.isArray(rawApis)) {
    return rawApis.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  if (typeof rawApis === "string") {
    return rawApis.split(",").map((item) => item.trim()).filter(Boolean);
  }
  const provider = String(route.provider ?? route.provider_id ?? "").trim();
  const api = String(route.api ?? route.api_id ?? route.name ?? "").trim();
  return provider && api ? [`${provider}/${api}`] : [];
}

export function parseStructuredModelApiRoutes(value: unknown): StructuredModelApiRoute[] {
  const parsed = parseJsonish(value);
  const root = parsed ?? value;
  let routes: unknown[] = [];
  if (Array.isArray(root)) {
    routes = root;
  } else if (root && typeof root === "object" && Array.isArray((root as Record<string, unknown>).routes)) {
    routes = (root as Record<string, unknown>).routes as unknown[];
  } else if (root && typeof root === "object" && Array.isArray((root as Record<string, unknown>).api_routes)) {
    routes = (root as Record<string, unknown>).api_routes as unknown[];
  }
  return routes
    .filter((route): route is Record<string, unknown> => !!route && typeof route === "object" && !Array.isArray(route))
    .map((route) => ({
      model: String(route.model ?? route.model_id ?? route.profile_id ?? "").trim(),
      apis: apiRefsFromRoute(route),
      raw: route,
    }))
    .filter((route) => route.model && route.apis.length > 0);
}

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
  const structured = parseStructuredModelApiRoutes(value).find((line) => line.model === target);
  if (structured) return [...structured.apis];
  const route = parseModelApiRouteLines(value).find((line) => line.kind === "route" && line.model === target);
  return route?.kind === "route" ? [...route.apis] : [];
}

export function updateModelApiRouteText(value: unknown, model: string, apis: string[]): string {
  const target = String(model ?? "").trim();
  if (!target) return String(value ?? "");
  const cleanedApis = apis.map((api) => String(api ?? "").trim()).filter(Boolean);
  const parsed = parseJsonish(value);
  if (parsed && (Array.isArray(parsed) || (typeof parsed === "object" && parsed !== null))) {
    const root: Record<string, unknown> = Array.isArray(parsed) ? { routes: parsed } : { ...(parsed as Record<string, unknown>) };
    const rawRoutes = Array.isArray(root.routes)
      ? [...root.routes]
      : Array.isArray(root.api_routes)
        ? [...root.api_routes]
        : [];
    let replacedStructured = false;
    const routes = rawRoutes
      .filter((route): route is Record<string, unknown> => !!route && typeof route === "object" && !Array.isArray(route))
      .map((route) => {
        const routeModel = String(route.model ?? route.model_id ?? route.profile_id ?? "").trim();
        if (routeModel !== target) return route;
        replacedStructured = true;
        return { ...route, model: target, apis: cleanedApis };
      })
      .filter((route) => {
        const routeModel = String(route.model ?? route.model_id ?? route.profile_id ?? "").trim();
        return routeModel !== target || cleanedApis.length > 0;
      });
    if (!replacedStructured && cleanedApis.length > 0) {
      routes.push({ model: target, apis: cleanedApis });
    }
    root.routes = routes;
    if ("api_routes" in root) delete root.api_routes;
    return JSON.stringify(root, null, 2) + "\n";
  }
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
