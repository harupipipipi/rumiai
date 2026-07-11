import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const reviewSource = readFileSync(new URL("./NavigationReview.tsx", import.meta.url), "utf8");

test("Search Home never schedules automatic destination navigation", () => {
  assert.doesNotMatch(appSource, /AUTO_NAV_DELAY_MS/);
  assert.doesNotMatch(appSource, /scheduleNavigation/);
  assert.match(appSource, /<NavigationReview/);
  assert.match(reviewSource, /Search Homeは自動では移動しません/);
});

test("Search Home validates every destination immediately before navigation", () => {
  assert.match(appSource, /reviewRouteDestination\(rawDestination\)/);
  assert.match(appSource, /window\.location\.assign\(destination\.url\)/);
  assert.doesNotMatch(appSource, /window\.location\.assign\(rawDestination\)/);
});

test("route shortcuts are not installed globally and sensitive route data is not wildcard-posted", () => {
  assert.doesNotMatch(appSource, /routeHotkeyActionFromKeyboardEvent/);
  assert.doesNotMatch(appSource, /routeNavigationForHotkey/);
  assert.doesNotMatch(appSource, /postMessage\([\s\S]*?,\s*["']\*["']\s*\)/);
});
