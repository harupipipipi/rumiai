(function initRumiBridgeUrlPolicy(globalScope) {
  "use strict";

  function validateServerUrl(value) {
    const raw = String(value || "").trim();
    if (!raw) {
      return { ok: false, message: "Bridge server URL is required." };
    }

    let parsed;
    try {
      parsed = new URL(raw);
    } catch (_error) {
      return { ok: false, message: "Bridge server URL must be a valid HTTP(S) URL." };
    }

    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return { ok: false, message: "Bridge server URL must use HTTP or HTTPS." };
    }

    if (parsed.username || parsed.password) {
      return { ok: false, message: "Bridge server URL must not include credentials." };
    }

    if (!isLocalOrPrivateHost(parsed.hostname)) {
      return { ok: false, message: "Bridge server URL must use a local or private host." };
    }

    return { ok: true, url: parsed.origin };
  }

  function normalizeServerUrl(value) {
    const result = validateServerUrl(value);
    return result.ok ? result.url : "";
  }

  function isLocalOrPrivateHost(hostname) {
    const host = String(hostname || "").trim().toLowerCase().replace(/^\[|\]$/g, "");
    if (!host) {
      return false;
    }
    if (host === "localhost" || host.endsWith(".localhost")) {
      return true;
    }
    if (isPrivateIpv4(host)) {
      return true;
    }
    return isPrivateIpv6(host);
  }

  function isPrivateIpv4(host) {
    const octets = host.split(".");
    if (octets.length !== 4) {
      return false;
    }
    const numbers = octets.map((part) => {
      if (!/^\d{1,3}$/.test(part)) {
        return Number.NaN;
      }
      const value = Number(part);
      return value >= 0 && value <= 255 ? value : Number.NaN;
    });
    if (numbers.some((value) => !Number.isInteger(value))) {
      return false;
    }

    const [a, b] = numbers;
    return (
      a === 10 ||
      a === 127 ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) ||
      (a === 169 && b === 254)
    );
  }

  function isPrivateIpv6(host) {
    if (host === "::1" || host === "0:0:0:0:0:0:0:1") {
      return true;
    }
    const firstHextet = host.split(":")[0];
    if (!/^[0-9a-f]{1,4}$/.test(firstHextet)) {
      return false;
    }
    const value = Number.parseInt(firstHextet, 16);
    return (value >= 0xfc00 && value <= 0xfdff) || (value >= 0xfe80 && value <= 0xfebf);
  }

  globalScope.RumiBridgeUrlPolicy = {
    validateServerUrl,
    normalizeServerUrl,
    isLocalOrPrivateHost
  };
})(globalThis);
