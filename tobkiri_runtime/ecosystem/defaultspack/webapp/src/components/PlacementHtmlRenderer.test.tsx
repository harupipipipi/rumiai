import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PlacementHtmlRenderer } from "./PlacementHtmlRenderer";

test("untrusted HTML renders an explicit extension boundary without an iframe", () => {
  const html = renderToStaticMarkup(
    createElement(PlacementHtmlRenderer, {
      manifest: {
        id: "html-test",
        label: "HTML test",
        source: { type: "custom", sourceId: "unsafe-extension" },
        renderer: { kind: "html", html: "<div>unsafe</div><script>alert(1)</script>" },
        placements: [{ surface: "right_sidebar", orientation: "vertical" }],
      },
    }),
  );

  assert.match(html, /role="status"/);
  assert.match(html, /Untrusted HTML blocked/);
  assert.match(html, /Source: custom:unsafe-extension/);
  assert.match(html, /verified component or declarative template/);
  assert.doesNotMatch(html, /<iframe/);
  assert.doesNotMatch(html, /srcdoc=/i);
  assert.doesNotMatch(html, /sandbox=/i);
  assert.doesNotMatch(html, /<script>alert\(1\)<\/script>/);
  assert.doesNotMatch(html, /<div>unsafe<\/div>/);
});
