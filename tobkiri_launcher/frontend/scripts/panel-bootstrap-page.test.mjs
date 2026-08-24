import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { dirname, resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const REPOSITORY_ROOT = resolve(SCRIPT_DIR, "../../..");
const RUNTIME_ROOT = resolve(REPOSITORY_ROOT, "tobkiri_runtime");

async function readBootstrapDocument() {
  const python = process.env.PYTHON || "python";
  const child = spawn(python, [
    "-u",
    "-c",
    [
      "import sys",
      "from core_runtime.pack_api_server import PackAPIServer",
      "from core_runtime.panel_auth import PanelAuthManager",
      "server = PackAPIServer(port=0, panel_auth_manager=PanelAuthManager(bootstrap_secret='test'))",
      "server.start()",
      "print(server.port, flush=True)",
      "sys.stdin.read()",
      "server.stop()",
    ].join("; "),
  ], {
    cwd: REPOSITORY_ROOT,
    env: {
      ...process.env,
      PYTHONDONTWRITEBYTECODE: "1",
      PYTHONPATH: RUNTIME_ROOT,
    },
    stdio: ["pipe", "pipe", "pipe"],
  });
  const exitPromise = once(child, "exit");
  const port = await new Promise((resolvePort, reject) => {
    let output = "";
    child.stdout.on("data", (chunk) => {
      output += String(chunk);
      const newline = output.indexOf("\n");
      if (newline >= 0) resolvePort(Number(output.slice(0, newline).trim()));
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      if (!output.includes("\n")) reject(new Error(`bootstrap server exited early: ${code}`));
    });
  });

  try {
    const response = await fetch(`http://127.0.0.1:${port}/panel/?code=stale-code`);
    assert.equal(response.status, 200);
    return await response.text();
  } finally {
    child.stdin.end();
    await exitPromise;
  }
}

const bootstrapDocumentPromise = readBootstrapDocument();

async function executeBootstrap({
  native = true,
  nativeFailure = null,
  freshExchangeSucceeds = true,
} = {}) {
  const html = await bootstrapDocumentPromise;
  const match = /<script>([\s\S]*?)<\/script>/.exec(html);
  assert.ok(match, "bootstrap document must contain one executable script");

  let href = "http://127.0.0.1/panel/?code=stale-code&view=packs#ready";
  let reloadCount = 0;
  let invokeCount = 0;
  const exchangeCodes = [];
  const storage = new Map();
  const message = {
    role: "status",
    textContent: "Authenticating with Tobkiri Launcher…",
    setAttribute(name, value) {
      if (name === "role") this.role = value;
    },
  };
  const location = {
    get href() {
      return href;
    },
    reload() {
      reloadCount += 1;
    },
  };
  const window = native ? {
    __TAURI__: {
      core: {
        async invoke(command) {
          assert.equal(command, "reauthorize_panel_session");
          invokeCount += 1;
          if (nativeFailure) throw nativeFailure;
          return "fresh-code";
        },
      },
    },
  } : {};

  vm.runInNewContext(match[1], {
    URL,
    document: {
      title: "Tobkiri",
      getElementById: (id) => id === "message" ? message : null,
    },
    fetch: async (_url, init) => {
      const { code } = JSON.parse(String(init?.body));
      exchangeCodes.push(code);
      const success = code === "fresh-code" && freshExchangeSucceeds;
      return {
        ok: success,
        status: success ? 200 : 401,
        json: async () => success
          ? { success: true, data: { csrf_token: "fresh-csrf" } }
          : { success: false, error: "Invalid or expired code" },
      };
    },
    history: {
      replaceState(_state, _title, target) {
        href = new URL(String(target), href).href;
      },
    },
    location,
    message,
    sessionStorage: {
      setItem(key, value) {
        storage.set(key, value);
      },
    },
    window,
  });

  for (let index = 0; index < 20 && reloadCount === 0 && message.role !== "alert"; index += 1) {
    await new Promise((resolveTurn) => setImmediate(resolveTurn));
  }
  return { exchangeCodes, href, invokeCount, message, reloadCount, storage };
}

test("pre-auth page renews one stale code, scrubs the URL, and reloads", async () => {
  const result = await executeBootstrap();

  assert.deepEqual(result.exchangeCodes, ["stale-code", "fresh-code"]);
  assert.equal(result.invokeCount, 1);
  assert.equal(result.reloadCount, 1);
  assert.equal(result.storage.get("rumi-panel-csrf"), "fresh-csrf");
  assert.equal(result.href, "http://127.0.0.1/panel/?view=packs#ready");
  assert.doesNotMatch(result.message.textContent, /stale-code|fresh-code/);
});

test("pre-auth page gives browser-only users a terminal accessible action", async () => {
  const result = await executeBootstrap({ native: false });

  assert.deepEqual(result.exchangeCodes, ["stale-code"]);
  assert.equal(result.invokeCount, 0);
  assert.equal(result.reloadCount, 0);
  assert.equal(result.message.role, "alert");
  assert.match(result.message.textContent, /Reopen this panel from Tobkiri Launcher/);
  assert.equal(result.href, "http://127.0.0.1/panel/?view=packs#ready");
});

test("pre-auth page stops after one failed fresh exchange", async () => {
  const result = await executeBootstrap({ freshExchangeSucceeds: false });

  assert.deepEqual(result.exchangeCodes, ["stale-code", "fresh-code"]);
  assert.equal(result.invokeCount, 1);
  assert.equal(result.reloadCount, 0);
  assert.equal(result.message.role, "alert");
  assert.match(result.message.textContent, /Reopen this panel from Tobkiri Launcher/);
});
