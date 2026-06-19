function originBase(env) {
  const raw = String(env.ORIGIN_BASE_URL || "").trim();
  if (!raw) {
    return null;
  }
  if (!/^https?:\/\//i.test(raw)) {
    throw new Error("ORIGIN_BASE_URL must start with http:// or https://");
  }
  return raw.replace(/\/+$/, "");
}

function targetUrl(request, origin) {
  const incoming = new URL(request.url);
  return `${origin}${incoming.pathname}${incoming.search}`;
}

async function forwardedRequest(request, origin) {
  const headers = new Headers(request.headers);
  const incoming = new URL(request.url);

  headers.delete("host");
  headers.delete("content-length");
  headers.delete("connection");
  headers.delete("keep-alive");
  headers.delete("transfer-encoding");
  headers.set("x-rumi-relay", "cloudflare-pages");
  headers.set("x-forwarded-host", incoming.host);

  const init = {
    method: request.method,
    headers,
    redirect: "manual"
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  return new Request(targetUrl(request, origin), init);
}

function relayResponse(response) {
  const headers = new Headers(response.headers);
  headers.delete("connection");
  headers.delete("keep-alive");
  headers.delete("transfer-encoding");
  headers.set("x-rumi-relay", "cloudflare-pages");

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers
  });
}

function missingOriginResponse() {
  return Response.json(
    {
      status: "error",
      code: "ORIGIN_NOT_CONFIGURED",
      message: "Set ORIGIN_BASE_URL on the Cloudflare Pages project before using this relay."
    },
    { status: 503 }
  );
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const origin = originBase(env);

  if (request.method === "GET" && url.pathname === "/api/relay-health") {
    return Response.json({
      status: "ok",
      relay: "cloudflare-pages",
      origin_configured: Boolean(origin),
      origin_base_url: origin || "",
      origin_health_url: origin ? `${origin}/api/health` : ""
    });
  }

  if (!origin) {
    return missingOriginResponse();
  }

  try {
    const response = await fetch(await forwardedRequest(request, origin));
    return relayResponse(response);
  } catch (error) {
    return Response.json(
      {
        status: "error",
        code: "ORIGIN_UNREACHABLE",
        message: "Cloudflare Pages relay could not reach the local defaultspack origin.",
        detail: error instanceof Error ? error.message : String(error)
      },
      { status: 502 }
    );
  }
}
