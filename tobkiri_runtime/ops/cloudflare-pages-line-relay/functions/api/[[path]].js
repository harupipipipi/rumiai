const LINE_WEBHOOK_PATH = "/api/integrations/line/webhook";
const ORIGIN_HEALTH_PATH = "/api/health";

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

async function forwardedRequest(request, origin, body = null) {
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
    init.body = body === null ? await request.arrayBuffer() : body;
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

function routeNotFoundResponse() {
  return Response.json(
    {
      status: "error",
      code: "ROUTE_NOT_FOUND",
      message: "This relay only exposes the LINE webhook and health endpoints."
    },
    { status: 404 }
  );
}

function methodNotAllowedResponse() {
  return Response.json(
    {
      status: "error",
      code: "METHOD_NOT_ALLOWED",
      message: "LINE webhook relay accepts POST requests only."
    },
    {
      status: 405,
      headers: { allow: "POST" }
    }
  );
}

function missingLineSecretResponse() {
  return Response.json(
    {
      status: "error",
      code: "LINE_SECRET_NOT_CONFIGURED",
      message: "Set LINE_CHANNEL_SECRET on the Cloudflare Pages project before using this relay."
    },
    { status: 503 }
  );
}

function invalidLineSignatureResponse(reason) {
  return Response.json(
    {
      status: "error",
      code: "SIGNATURE_INVALID",
      message: reason
    },
    { status: 401 }
  );
}

function base64FromArrayBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function timingSafeEqual(left, right) {
  if (left.length !== right.length) {
    return false;
  }
  let result = 0;
  for (let index = 0; index < left.length; index += 1) {
    result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return result === 0;
}

async function expectedLineSignature(secret, body) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const digest = await crypto.subtle.sign("HMAC", key, body);
  return base64FromArrayBuffer(digest);
}

async function verifyLineSignature(request, env, body) {
  const secret = String(env.LINE_CHANNEL_SECRET || "").trim();
  if (!secret) {
    return { ok: false, response: missingLineSecretResponse() };
  }

  const signature = String(request.headers.get("x-line-signature") || "").trim();
  if (!signature) {
    return { ok: false, response: invalidLineSignatureResponse("missing LINE signature header") };
  }

  const expected = await expectedLineSignature(secret, body);
  if (!timingSafeEqual(expected, signature)) {
    return { ok: false, response: invalidLineSignatureResponse("LINE signature mismatch") };
  }

  return { ok: true, response: null };
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  const url = new URL(request.url);
  const origin = originBase(env);

  if (request.method === "GET" && url.pathname === "/api/relay-health") {
    return Response.json({
      status: "ok",
      relay: "cloudflare-pages",
      origin_configured: Boolean(origin),
      line_signature_secret_configured: Boolean(String(env.LINE_CHANNEL_SECRET || "").trim()),
      forwarded_paths: [LINE_WEBHOOK_PATH, ORIGIN_HEALTH_PATH]
    });
  }

  if (!origin) {
    return missingOriginResponse();
  }

  if (request.method === "GET" && url.pathname === ORIGIN_HEALTH_PATH) {
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

  if (url.pathname !== LINE_WEBHOOK_PATH) {
    return routeNotFoundResponse();
  }

  if (request.method !== "POST") {
    return methodNotAllowedResponse();
  }

  const body = await request.arrayBuffer();
  const verification = await verifyLineSignature(request, env, body);
  if (!verification.ok) {
    return verification.response;
  }

  try {
    const response = await fetch(await forwardedRequest(request, origin, body));
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
