/** A customer orders in the Mini App; the owner accepts it in the dashboard; the customer sees
 * the new status. Exercises the real backend end to end (pricing, idempotent checkout, RLS,
 * transitions). */
import { expect, type Page, test } from "@playwright/test";

import { DASHBOARD, MINIAPP } from "../playwright.config";

const seed = JSON.parse(process.env.SOP_E2E ?? "{}") as {
  owner_email: string;
  owner_password: string;
};

async function offlineTelegramScript(page: Page) {
  // Outside Telegram the official script only provides an empty WebApp; keep tests offline.
  await page.route("https://telegram.org/**", (r) =>
    r.fulfill({ contentType: "text/javascript", body: "" }),
  );
}

test.describe.configure({ mode: "serial" });

let orderNumber = "";

test("customer places a pickup order in the Mini App", async ({ page }) => {
  await offlineTelegramScript(page);
  await page.goto(MINIAPP);
  await page.getByText("Beef shawarma").first().click();
  await expect(page).toHaveURL(/\/p\//);
  await page.getByRole("button", { name: /Add to cart/ }).click();

  await page.getByRole("link", { name: /View cart/ }).click();
  await expect(page).toHaveURL(/\/cart/);
  await page.getByRole("button", { name: /Checkout/ }).click();

  await page.getByRole("button", { name: /Pickup/ }).click();
  await expect(page.getByRole("button", { name: /Pickup/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Name").fill("E2E Customer");
  await page.getByLabel("Mobile number").fill("07701234567");
  await page.getByRole("button", { name: /Place order/ }).click();

  await expect(page.getByText("Order received!")).toBeVisible();
  orderNumber = (await page.getByText(/Order #\d+/).innerText()).match(/#(\d+)/)?.[1] ?? "";
  expect(orderNumber).not.toBe("");
});

test("owner accepts the order in the dashboard", async ({ browser }) => {
  // Staff work on a desktop/tablet: full sidebar.
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "en-US" });
  const page = await ctx.newPage();
  await page.addInitScript(() => localStorage.setItem("sop.dashboard.lang", "en"));
  await page.goto(DASHBOARD);
  await page.getByLabel("Email or phone").fill(seed.owner_email);
  await page.getByLabel("Password").fill(seed.owner_password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await page.getByRole("link", { name: "Orders" }).first().click();
  await page.getByText(`#${orderNumber}`, { exact: true }).click();
  await page.getByRole("button", { name: "Accept" }).click();
  await expect(page.getByRole("dialog").getByText("Confirmed").first()).toBeVisible();
  await ctx.close();
});

test("customer sees the accepted status", async ({ page }) => {
  await offlineTelegramScript(page);
  await page.goto(`${MINIAPP}/orders`);
  const card = page.getByRole("link").filter({ hasText: `#${orderNumber}` });
  await expect(card).toContainText("Confirmed");
});
