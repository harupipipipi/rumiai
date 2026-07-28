import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import {
  TOBKIRI_LOADING_ANIMATION_URL,
  TOBKIRI_LOADING_LABEL,
  TobkiriLoadingScreen,
} from "./TobkiriLoadingScreen";
import { HostBootstrap } from "../host/HostBootstrap";

test("renders the Tobkiri Launcher animation as the accessible shell loading state", () => {
  const markup = renderToStaticMarkup(<TobkiriLoadingScreen />);

  assert.match(markup, /role="status"/);
  assert.match(markup, new RegExp(`aria-label="${TOBKIRI_LOADING_LABEL}"`));
  assert.match(markup, /aria-live="polite"/);
  assert.match(markup, /data-tobkiri-loading-screen=""/);
  assert.match(markup, /data-loading-scene="launcher"/);
  assert.match(markup, new RegExp(`src="${TOBKIRI_LOADING_ANIMATION_URL}"`));
  assert.match(markup, /motion-reduce:hidden/);
  assert.match(markup, /hidden aspect-\[2\/1\].*motion-reduce:flex/);
  assert.match(markup, />Tobkiri</);
  assert.doesNotMatch(markup, /Loading selected interface/);
});

test("uses the branded loading screen while the dynamic interface catalog loads", () => {
  const markup = renderToStaticMarkup(
    <HostBootstrap route="/chat" fallback={<div>Fallback</div>} />,
  );

  assert.match(markup, /data-tobkiri-loading-screen=""/);
  assert.doesNotMatch(markup, /Fallback/);
  assert.doesNotMatch(markup, /Loading selected interface/);
});

test("vendors the exact local animation shipped by Tobkiri Launcher", async () => {
  const defaultspackAsset = await readFile(
    new URL("../../public/assets/tobkiri-startup-blade-cut.svg", import.meta.url),
  );
  const launcherAsset = await readFile(
    new URL(
      "../../../../../../tobkiri_launcher/frontend/public/assets/tobkiri-startup-blade-cut.svg",
      import.meta.url,
    ),
  );

  assert.deepEqual(defaultspackAsset, launcherAsset);
});
