import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  readJsonLocalStorage,
  safeLocalStorageGetItem,
  safeLocalStorageRemoveItem,
  safeLocalStorageSetItem,
  useLocalStorage,
  writeJsonLocalStorage,
} from "./useLocalStorage";

function restoreLocalStorage(
  previousDescriptor: PropertyDescriptor | undefined,
): void {
  if (previousDescriptor) {
    Object.defineProperty(globalThis, "localStorage", previousDescriptor);
  } else {
    Reflect.deleteProperty(globalThis, "localStorage");
  }
}

function withLocalStorageDescriptor<T>(
  descriptor: PropertyDescriptor,
  run: () => T,
): T {
  const previousDescriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    "localStorage",
  );
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    ...descriptor,
  });
  try {
    return run();
  } finally {
    restoreLocalStorage(previousDescriptor);
  }
}

function fakeStorage(
  methods: Partial<Pick<Storage, "getItem" | "setItem" | "removeItem">>,
): Storage {
  return {
    length: 0,
    clear: () => undefined,
    getItem: methods.getItem ?? (() => null),
    key: () => null,
    removeItem: methods.removeItem ?? (() => undefined),
    setItem: methods.setItem ?? (() => undefined),
  };
}

function restrictedStorageError(): DOMException {
  return new DOMException("Storage access is restricted.", "SecurityError");
}

function quotaStorageError(): DOMException {
  return new DOMException("Storage quota exceeded.", "QuotaExceededError");
}

function LocalStorageProbe() {
  const [value] = useLocalStorage(
    "rumi-safe-localstorage-test",
    "fallback",
  );
  return createElement("span", null, value);
}

test("safe localStorage helpers preserve working storage behavior", () => {
  const values = new Map<string, string>([
    ["stored-string", JSON.stringify("saved")],
    ["stored-false", "false"],
  ]);

  withLocalStorageDescriptor(
    {
      value: fakeStorage({
        getItem: (key) => values.get(key) ?? null,
        setItem: (key, value) => {
          values.set(key, value);
        },
        removeItem: (key) => {
          values.delete(key);
        },
      }),
    },
    () => {
      assert.equal(
        safeLocalStorageGetItem("stored-string"),
        JSON.stringify("saved"),
      );
      assert.equal(readJsonLocalStorage("stored-string", "fallback"), "saved");
      assert.equal(readJsonLocalStorage("stored-false", true), false);
      assert.equal(
        writeJsonLocalStorage("stored-object", { enabled: true }),
        true,
      );
      assert.equal(
        values.get("stored-object"),
        JSON.stringify({ enabled: true }),
      );
      assert.equal(safeLocalStorageSetItem("raw", "value"), true);
      assert.equal(values.get("raw"), "value");
      assert.equal(safeLocalStorageRemoveItem("raw"), true);
      assert.equal(values.has("raw"), false);
    },
  );
});

test("localStorage setItem exceptions are non-fatal", () => {
  withLocalStorageDescriptor(
    {
      value: fakeStorage({
        setItem: () => {
          throw quotaStorageError();
        },
      }),
    },
    () => {
      assert.doesNotThrow(() => {
        assert.equal(safeLocalStorageSetItem("blocked", "value"), false);
        assert.equal(writeJsonLocalStorage("blocked", { value: true }), false);
      });
    },
  );
});

test("safe localStorage helpers tolerate restricted storage getters", () => {
  withLocalStorageDescriptor(
    {
      get() {
        throw restrictedStorageError();
      },
    },
    () => {
      assert.equal(safeLocalStorageGetItem("blocked"), null);
      assert.equal(readJsonLocalStorage("blocked", "fallback"), "fallback");
      assert.equal(safeLocalStorageSetItem("blocked", "value"), false);
      assert.equal(writeJsonLocalStorage("blocked", { value: true }), false);
      assert.equal(safeLocalStorageRemoveItem("blocked"), false);
    },
  );
});

test("safe helpers tolerate throwing read and remove operations", () => {
  withLocalStorageDescriptor(
    {
      value: fakeStorage({
        getItem: () => {
          throw restrictedStorageError();
        },
        removeItem: () => {
          throw restrictedStorageError();
        },
      }),
    },
    () => {
      assert.equal(safeLocalStorageGetItem("blocked"), null);
      assert.equal(readJsonLocalStorage("blocked", { ok: false }).ok, false);
      assert.equal(safeLocalStorageRemoveItem("blocked"), false);
    },
  );
});

test("JSON serialization exceptions are non-fatal", () => {
  const cyclic: { self?: unknown } = {};
  cyclic.self = cyclic;
  withLocalStorageDescriptor({ value: fakeStorage({}) }, () => {
    assert.doesNotThrow(() => {
      assert.equal(writeJsonLocalStorage("cyclic", cyclic), false);
    });
  });
});

test("readJsonLocalStorage falls back for malformed data", () => {
  withLocalStorageDescriptor(
    {
      value: fakeStorage({
        getItem: (key) => (key === "broken" ? "{" : null),
      }),
    },
    () => {
      assert.equal(readJsonLocalStorage("broken", "fallback"), "fallback");
      assert.equal(readJsonLocalStorage("missing", "fallback"), "fallback");
    },
  );
});

test("useLocalStorage survives rendering when storage is restricted", () => {
  withLocalStorageDescriptor(
    {
      get() {
        throw restrictedStorageError();
      },
    },
    () => {
      const html = renderToStaticMarkup(createElement(LocalStorageProbe));
      assert.match(html, /fallback/);
    },
  );
});

test("useLocalStorage renders stored values when storage is available", () => {
  withLocalStorageDescriptor(
    {
      value: fakeStorage({
        getItem: (key) =>
          key === "rumi-safe-localstorage-test"
            ? JSON.stringify("stored")
            : null,
      }),
    },
    () => {
      const html = renderToStaticMarkup(createElement(LocalStorageProbe));
      assert.match(html, /stored/);
    },
  );
});
