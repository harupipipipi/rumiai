import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PlacementHtmlRenderer } from "./PlacementHtmlRenderer";

test("sandboxed html renderer keeps untrusted content in an opaque restricted iframe", () => {
  const html = renderToStaticMarkup(
    createElement(PlacementHtmlRenderer, {
      manifest: {
        id: "html-test",
        label: "HTML test",
        source: { type: "custom" },
        renderer: { kind: "html", html: "<div>unsafe</div><script>alert(1)</script>" },
        placements: [{ surface: "right_sidebar", orientation: "vertical" }],
      },
    }),
  );

  assert.match(html, /<iframe/);
  assert.match(html, /sandbox=""/);
  assert.match(html, /referrerpolicy="no-referrer"/i);
  assert.match(html, /loading="lazy"/);
  assert.doesNotMatch(html, /allow-same-origin/);
  assert.doesNotMatch(html, /<script>alert\(1\)<\/script>/);
  assert.match(html, /Content-Security-Policy/);
});
