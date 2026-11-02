/** WCAG 2.1 AA (NFR-8): automated axe scan of the main Mini App and dashboard screens. */
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

import { DASHBOARD, MINIAPP } from "../playwright.config";

const seed = JSON.parse(process.env.SOP_E2E ?? "{}") as {
  owner_email: string;
  owner_password: string;
};

async function expectAccessible(page: Page, screen: string) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const summary = violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.nodes
        .slice(0, 3)
        .map(
          (n) =>
            `${n.target.join(" ")} ${n.html.slice(0, 120)} ${(n.failureSummary ?? "").split("\n").pop()}`,
        )
        .join(" | ")}`,
  );
  expect.soft(summary, `${screen}: accessibility violations`).toEqual([]);
}

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`${colorScheme} theme`, () => {
    // Scan the settled UI: entrance animations (opacity) would skew contrast results.
    test.use({ reducedMotion: "reduce", colorScheme });

    test("Mini App screens are accessible", async ({ page }) => {
      await page.route("https://telegram.org/**", (r) =>
        r.fulfill({ contentType: "text/javascript", body: "" }),
      );
      await page.goto(MINIAPP);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expectAccessible(page, "home");

      await page.getByText("Double burger").first().click();
      await expect(
        page.getByRole("button", { name: /Add to cart/ }),
      ).toBeVisible();
      await expectAccessible(page, "product");
      await page.getByRole("button", { name: /Add to cart/ }).click();

      await page.goto(`${MINIAPP}/cart`);
      await expect(
        page.getByRole("button", { name: /Checkout/ }),
      ).toBeVisible();
      await expectAccessible(page, "cart");

      await page.getByRole("button", { name: /Checkout/ }).click();
      await expect(page.getByLabel("Name")).toBeVisible();
      await expectAccessible(page, "checkout");

      for (const path of ["/orders", "/profile", "/categories"]) {
        await page.goto(`${MINIAPP}${path}`);
        await page.waitForLoadState("networkidle");
        await expectAccessible(page, path);
      }
    });

    test("dashboard screens are accessible", async ({ browser }) => {
      const ctx = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        reducedMotion: "reduce",
        colorScheme,
      });
      const page = await ctx.newPage();
      await page.addInitScript(() =>
        localStorage.setItem("sop.dashboard.lang", "en"),
      );
      await page.goto(DASHBOARD);
      await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
      await expectAccessible(page, "login");

      await page.getByLabel("Email or phone").fill(seed.owner_email);
      await page.getByLabel("Password").fill(seed.owner_password);
      await page.getByRole("button", { name: "Sign in" }).click();
      await expect(
        page.getByRole("link", { name: "Orders" }).first(),
      ).toBeVisible();
      await page.waitForLoadState("networkidle");
      await expectAccessible(page, "overview");

      for (const name of ["Orders", "Products", "Customers", "Settings"]) {
        await page.getByRole("link", { name }).first().click();
        await page.waitForLoadState("networkidle");
        await expectAccessible(page, name);
      }
      await ctx.close();
    });
  });
}
