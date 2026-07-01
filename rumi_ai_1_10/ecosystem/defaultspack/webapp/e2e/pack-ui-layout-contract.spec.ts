import { test, expect, type Route } from "@playwright/test";

async function ok(route: Route, data: unknown) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", data }) });
}

test("pack UI layout contract smoke", async ({ page }) => {
  await page.route("**/api/**", async (route) => ok(route, {}));
  await page.goto("/chat");
  await expect(page.locator("body")).toBeVisible();
});
