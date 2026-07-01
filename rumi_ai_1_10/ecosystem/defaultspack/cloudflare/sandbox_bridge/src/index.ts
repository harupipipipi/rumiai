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
};

export default bridge(
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
