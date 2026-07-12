import { bridge } from "@cloudflare/sandbox/bridge";
import type { Sandbox } from "@cloudflare/sandbox";
import type { WarmPool } from "@cloudflare/sandbox/bridge";

export { Sandbox } from "@cloudflare/sandbox";
export { WarmPool } from "@cloudflare/sandbox/bridge";

type Env = {
  Sandbox: DurableObjectNamespace<Sandbox>;
  WarmPool: DurableObjectNamespace<WarmPool>;
  SANDBOX_API_KEY?: string;
  WARM_POOL_TARGET?: string;
  WARM_POOL_REFRESH_INTERVAL?: string;
  [key: string]: unknown;
};

const bridgeHandler = bridge(
  {
    async fetch(request: Request, _env: Env): Promise<Response> {
      const url = new URL(request.url);
      if (url.pathname === "/") {
        return Response.json({
          ok: true,
          service: "rumi-cloudflare-sandbox-bridge",
          bridge: "/v1",
          health: "/health",
        });
      }
      return new Response("Not Found", { status: 404 });
    },
  },
  {
    apiRoutePrefix: "/v1",
    healthRoute: "/health",
  },
);
type BridgeFetch = NonNullable<typeof bridgeHandler.fetch>;

export default {
  ...bridgeHandler,
  async fetch(
    request: Parameters<BridgeFetch>[0],
    env: Env,
    ctx: Parameters<BridgeFetch>[2],
  ): Promise<Response> {
    const url = new URL(request.url);
    if (isBridgeApiRoute(url.pathname)) {
      const authFailure = await authenticateBridgeRequest(request, env);
      if (authFailure) {
        return authFailure;
      }
    }
    return bridgeHandler.fetch?.(request, env, ctx) ?? new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;

function isBridgeApiRoute(pathname: string): boolean {
  return pathname === "/v1" || pathname.startsWith("/v1/");
}

async function authenticateBridgeRequest(request: { headers: Headers }, env: Env): Promise<Response | null> {
  const expectedToken = env.SANDBOX_API_KEY?.trim();
  if (!expectedToken) {
    return authJson(
      {
        error: "Sandbox Bridge API key is not configured.",
        code: "sandbox_api_key_missing",
      },
      503,
    );
  }

  const providedToken = bearerToken(request.headers.get("Authorization"));
  if (!providedToken || !(await timingSafeBearerTokenMatches(providedToken, expectedToken))) {
    return authJson({ error: "Unauthorized", code: "unauthorized" }, 401, {
      "WWW-Authenticate": "Bearer",
    });
  }

  return null;
}

function bearerToken(header: string | null): string | null {
  const match = /^Bearer\s+(.+)$/i.exec(header ?? "");
  return match?.[1]?.trim() || null;
}

async function timingSafeBearerTokenMatches(provided: string, expected: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const [providedDigest, expectedDigest] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(provided)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ]);
  const providedBytes = new Uint8Array(providedDigest);
  const expectedBytes = new Uint8Array(expectedDigest);
  let diff = providedBytes.length ^ expectedBytes.length;
  for (let index = 0; index < providedBytes.length && index < expectedBytes.length; index += 1) {
    diff |= providedBytes[index] ^ expectedBytes[index];
  }
  return diff === 0;
}

function authJson(body: { error: string; code: string }, status: number, headers: HeadersInit = {}): Response {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": "no-store",
      ...headers,
    },
  });
}
