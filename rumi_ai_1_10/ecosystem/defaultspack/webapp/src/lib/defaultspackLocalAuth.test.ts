import test from "node:test";
import assert from "node:assert/strict";

import { defaultspackUrlWithLocalAuthToken } from "./defaultspackLocalAuth";

function withWindowOrigin(origin: string, run: () => void): void {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { origin } },
  });
  try {
    run();
  } finally {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  }
}

test("local auth helper tokenizes an unambiguous root-relative same-origin path", () => {
  assert.equal(
    defaultspackUrlWithLocalAuthToken("/approval?request_id=req-1#view=compact", "tok/en"),
    "/approval?request_id=req-1#view=compact&rumi_local_auth=tok%2Fen",
  );
  assert.equal(
    defaultspackUrlWithLocalAuthToken("/approval#rumi_local_auth=existing", "new-token"),
    "/approval#rumi_local_auth=existing",
  );
});

test("local auth helper accepts an absolute URL only when the browser origin matches", () => {
  withWindowOrigin("https://rumi.example", () => {
    assert.equal(
      defaultspackUrlWithLocalAuthToken("https://rumi.example/approval?request_id=req-2", "secret"),
      "/approval?request_id=req-2#rumi_local_auth=secret",
    );
    assert.equal(
      defaultspackUrlWithLocalAuthToken("settings/account", "secret"),
      "/settings/account#rumi_local_auth=secret",
    );
  });
});

test("local auth helper never appends a credential to external or ambiguous destinations", () => {
  withWindowOrigin("https://rumi.example", () => {
    const unsafe = [
      "https://attacker.example/collect",
      "//attacker.example/collect",
      "//rumi.example/approval",
      "javascript:alert(1)",
      "data:text/html,hello",
      "file:///tmp/secret",
      "rumi-custom:approval",
      "https://user:password@rumi.example/approval",
      "http://[::1",
      "/approval\u0000https://attacker.example",
    ];

    for (const destination of unsafe) {
      assert.equal(defaultspackUrlWithLocalAuthToken(destination, "never-leak"), destination);
      assert.equal(defaultspackUrlWithLocalAuthToken(destination, "never-leak").includes("never-leak"), false);
    }
  });
});

test("local auth helper stays fail-closed for absolute URLs without a browser origin", () => {
  assert.equal(
    defaultspackUrlWithLocalAuthToken("https://127.0.0.1/approval", "secret"),
    "https://127.0.0.1/approval",
  );
});
