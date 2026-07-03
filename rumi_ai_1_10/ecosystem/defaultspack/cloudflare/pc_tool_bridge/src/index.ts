type Env = {
  RUMI_PC_ORIGIN?: string;
  RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME?: string;
  RUMI_PC_TOOL_BRIDGE_TOKEN?: string;
  RUMI_PC_RUNTIME_BEARER?: string;
  RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN?: string;
};

type ProxyRoute = {
  method: string;
  pattern: RegExp;
  target: string | ((match: RegExpExecArray) => string);
  passQuery?: boolean;
};

const PROXY_ROUTES: ProxyRoute[] = [
  {
    method: "GET",
    pattern: /^\/v1\/catalog\/?$/,
    target: "/api/tools/catalog",
    passQuery: true,
  },
  {
    method: "GET",
    pattern: /^\/v1\/tools\/names\/?$/,
    target: "/api/tools/names",
    passQuery: true,
  },
  {
    method: "POST",
    pattern: /^\/v1\/tools\/invoke\/?$/,
    target: "/api/tools/invoke",
  },
  {
    method: "GET",
    pattern: /^\/v1\/authority\/requests\/?$/,
    target: "/api/authority/requests",
    passQuery: true,
  },
  {
    method: "GET",
    pattern: /^\/v1\/authority\/requests\/([^/]+)\/?$/,
    target: (match) => `/api/authority/requests/${encodeURIComponent(decodeURIComponent(match[1] ?? ""))}`,
  },
  {
    method: "POST",
    pattern: /^\/v1\/authority\/requests\/([^/]+)\/(challenge|approve|deny)\/?$/,
    target: (match) => {
      const action = match[2] ?? "";
      return `/api/authority/requests/${encodeURIComponent(decodeURIComponent(match[1] ?? ""))}/${action}`;
    },
  },
];

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      const cors = corsHeaders(request, env);
      if (request.headers.get("Origin") && cors === null) {
        return json({ ok: false, error: "cors_origin_not_allowed" }, 403);
      }
      return new Response(null, {
        status: 204,
        headers: cors ?? new Headers({ "Cache-Control": "no-store" }),
      });
    }

    if (url.pathname === "/" && request.method === "GET") {
      return json({
        ok: true,
        service: "rumi-cloudflare-pc-tool-bridge",
        health: "/health",
        bridge: "/v1",
      }, 200, corsHeaders(request, env));
    }

    if (url.pathname === "/health" && request.method === "GET") {
      return json(health(env), 200, corsHeaders(request, env));
    }

    const route = matchRoute(request.method, url.pathname);
    if (route === null) {
      return json({ ok: false, error: "not_found" }, 404, corsHeaders(request, env));
    }

    const auth = await bridgeAuthorized(request, env);
    if (!auth.ok) {
      return json({ ok: false, error: auth.error }, auth.status, corsHeaders(request, env));
    }

    const origin = normalizePcOrigin(env);
    if (!origin.ok) {
      return json({ ok: false, error: origin.error }, 503, corsHeaders(request, env));
    }

    const runtimeBearer = (env.RUMI_PC_RUNTIME_BEARER ?? "").trim();
    if (runtimeBearer.length === 0) {
      return json({ ok: false, error: "pc_runtime_bearer_not_configured" }, 503, corsHeaders(request, env));
    }

    return proxyToPc(request, url, route, origin.url, runtimeBearer, corsHeaders(request, env));
  },
};

function health(env: Env): Record<string, unknown> {
  const origin = normalizePcOrigin(env);
  return {
    ok: origin.ok && Boolean((env.RUMI_PC_TOOL_BRIDGE_TOKEN ?? "").trim()) && Boolean((env.RUMI_PC_RUNTIME_BEARER ?? "").trim()),
    service: "rumi-cloudflare-pc-tool-bridge",
    pc_origin_configured: origin.ok,
    pc_origin_error: origin.ok ? undefined : origin.error,
    client_token_configured: Boolean((env.RUMI_PC_TOOL_BRIDGE_TOKEN ?? "").trim()),
    pc_runtime_bearer_configured: Boolean((env.RUMI_PC_RUNTIME_BEARER ?? "").trim()),
    cors_allowed_origin_configured: Boolean((env.RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN ?? "").trim()),
    routes: [
      "GET /v1/catalog",
      "GET /v1/tools/names",
      "POST /v1/tools/invoke",
      "GET /v1/authority/requests",
      "GET /v1/authority/requests/:id",
      "POST /v1/authority/requests/:id/challenge",
      "POST /v1/authority/requests/:id/approve",
      "POST /v1/authority/requests/:id/deny",
    ],
  };
}

function matchRoute(method: string, pathname: string): { route: ProxyRoute; match: RegExpExecArray } | null {
  const normalizedMethod = method.toUpperCase();
  for (const route of PROXY_ROUTES) {
    if (route.method !== normalizedMethod) continue;
    const match = route.pattern.exec(pathname);
    if (match !== null) {
      return { route, match };
    }
  }
  return null;
}

async function proxyToPc(
  request: Request,
  requestUrl: URL,
  matched: { route: ProxyRoute; match: RegExpExecArray },
  pcOrigin: URL,
  runtimeBearer: string,
  cors: Headers | null,
): Promise<Response> {
  const path = typeof matched.route.target === "function" ? matched.route.target(matched.match) : matched.route.target;
  const upstreamUrl = new URL(path, pcOrigin);
  if (matched.route.passQuery) {
    upstreamUrl.search = requestUrl.search;
  }

  const headers = upstreamHeaders(request.headers, runtimeBearer);
  const init: RequestInit = {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    redirect: "manual",
  };

  const upstream = await fetch(upstreamUrl, init);
  const responseHeaders = responseHeadersFor(upstream.headers);
  responseHeaders.set("X-Rumi-Cloudflare-Bridge", "pc-tool-bridge");
  if (cors !== null) {
    for (const [key, value] of cors) {
      responseHeaders.set(key, value);
    }
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

function upstreamHeaders(input: Headers, runtimeBearer: string): Headers {
  const headers = new Headers();
  const accept = input.get("Accept");
  const contentType = input.get("Content-Type");
  if (accept) headers.set("Accept", accept);
  if (contentType) headers.set("Content-Type", contentType);
  headers.set("Authorization", `Bearer ${runtimeBearer}`);
  headers.set("X-Rumi-Client", "rumi-cloudflare-pc-tool-bridge");
  return headers;
}

function responseHeadersFor(input: Headers): Headers {
  const headers = new Headers();
  for (const [key, value] of input) {
    const lower = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lower)) continue;
    if (lower === "set-cookie") continue;
    headers.set(key, value);
  }
  return headers;
}

async function bridgeAuthorized(request: Request, env: Env): Promise<{ ok: true } | { ok: false; status: number; error: string }> {
  const expected = (env.RUMI_PC_TOOL_BRIDGE_TOKEN ?? "").trim();
  if (expected.length === 0) {
    return { ok: false, status: 503, error: "bridge_token_not_configured" };
  }
  const provided = bearerToken(request.headers.get("Authorization") ?? "");
  if (provided.length === 0) {
    return { ok: false, status: 401, error: "bridge_token_required" };
  }
  const allowed = await timingSafeTokenEqual(provided, expected);
  if (!allowed) {
    return { ok: false, status: 403, error: "bridge_token_invalid" };
  }
  return { ok: true };
}

function bearerToken(value: string): string {
  const match = /^Bearer\s+(.+)$/i.exec(value.trim());
  return match?.[1]?.trim() ?? "";
}

async function timingSafeTokenEqual(left: string, right: string): Promise<boolean> {
  const [leftDigest, rightDigest] = await Promise.all([sha256(left), sha256(right)]);
  if (leftDigest.byteLength !== rightDigest.byteLength) return false;
  let diff = 0;
  for (let i = 0; i < leftDigest.byteLength; i += 1) {
    diff |= (leftDigest[i] ?? 0) ^ (rightDigest[i] ?? 0);
  }
  return diff === 0;
}

async function sha256(value: string): Promise<Uint8Array> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return new Uint8Array(digest);
}

function normalizePcOrigin(env: Env): { ok: true; url: URL } | { ok: false; error: string } {
  const rawOrigin = (env.RUMI_PC_ORIGIN ?? "").trim();
  const rawHostname = (env.RUMI_CLOUDFLARE_PC_TUNNEL_HOSTNAME ?? "").trim();
  const raw = rawOrigin || rawHostname;
  if (raw.length === 0) return { ok: false, error: "pc_origin_not_configured" };

  const candidate = raw.includes("://") ? raw : `https://${raw}`;
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return { ok: false, error: "pc_origin_invalid" };
  }

  if (parsed.protocol !== "https:") {
    return { ok: false, error: "pc_origin_must_be_https" };
  }
  if (parsed.pathname !== "/" || parsed.search || parsed.hash) {
    return { ok: false, error: "pc_origin_must_not_include_path_query_or_hash" };
  }

  const hostname = parsed.hostname.toLowerCase();
  if (hostname.endsWith(".pages.dev")) {
    return { ok: false, error: "pages_dev_is_not_a_pc_tunnel_hostname" };
  }
  if (hostname.endsWith(".trycloudflare.com")) {
    return { ok: false, error: "trycloudflare_is_not_stable" };
  }
  if (isPrivateOrLoopbackHostname(hostname)) {
    return { ok: false, error: "pc_origin_must_be_public_tunnel_hostname" };
  }
  return { ok: true, url: parsed };
}

function isPrivateOrLoopbackHostname(hostname: string): boolean {
  if (hostname === "localhost" || hostname.endsWith(".local")) return true;
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(hostname)) {
    const parts = hostname.split(".").map((part) => Number.parseInt(part, 10));
    const a = parts[0] ?? -1;
    const b = parts[1] ?? -1;
    if (a === 10 || a === 127 || a === 0) return true;
    if (a === 192 && b === 168) return true;
    if (a === 172 && b >= 16 && b <= 31) return true;
    if (a === 169 && b === 254) return true;
  }
  if (hostname.includes(":")) return true;
  return false;
}

function json(data: Record<string, unknown>, status = 200, extraHeaders: Headers | null = null): Response {
  const headers = new Headers({
    "Cache-Control": "no-store",
  });
  if (extraHeaders !== null) {
    for (const [key, value] of extraHeaders) {
      headers.set(key, value);
    }
  }
  return Response.json(data, {
    status,
    headers,
  });
}

function corsHeaders(request: Request, env: Env): Headers | null {
  const origin = request.headers.get("Origin");
  if (!origin) return null;
  const allowed = (env.RUMI_PC_TOOL_BRIDGE_ALLOWED_ORIGIN ?? "").trim();
  if (allowed.length === 0 || allowed !== origin) {
    return null;
  }
  const headers = new Headers();
  headers.set("Access-Control-Allow-Origin", origin);
  headers.set("Vary", "Origin");
  headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept");
  headers.set("Access-Control-Max-Age", "600");
  return headers;
}
