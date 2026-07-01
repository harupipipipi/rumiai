import { test, expect } from "@playwright/test";

test("pack UI layout contract placeholder", async ({ page }) => {
  await page.goto("/chat");
  await expect(page.locator("body")).toBeVisible();
});
