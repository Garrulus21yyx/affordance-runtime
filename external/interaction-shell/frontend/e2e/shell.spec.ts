import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("one Console joins real user interaction, live surface, and Labs", async ({ page }) => {
  let diagnosticsReads = 0;
  let labReads = 0;
  const commandPaths: string[] = [];
  page.on("request", (outgoing) => {
    const path = new URL(outgoing.url()).pathname;
    if (outgoing.method() === "GET" && path.endsWith("/labs/completed-runs")) diagnosticsReads += 1;
    if (outgoing.method() === "GET" && path.includes("/shell-api/labs/")) labReads += 1;
    if (outgoing.method() === "POST" && path.includes("/shell-api/sessions/")) commandPaths.push(path);
  });

  await page.goto("/");
  await expect(page.getByTestId("surface-unavailable")).toBeVisible();
  await expect(page.getByText("Affordance", { exact: true })).toBeVisible();
  expect(labReads).toBe(0);
  expect(diagnosticsReads).toBe(0);

  const composer = page.getByRole("textbox", { name: "Task command" });
  await composer.fill("Choose an option");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("pending-question")).toContainText("Which option");
  await composer.fill("The second one");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("confirmation-dialog")).toBeVisible();
  await page.getByRole("button", { name: "批准操作" }).click();
  await expect(page.getByTestId("completion")).toContainText("Contract demo completed");
  expect(commandPaths).toHaveLength(3);
  expect(commandPaths.every((path) => path.endsWith("/commands"))).toBe(true);

  await page.getByRole("button", { name: "Labs" }).click();
  await expect(page.getByRole("heading", { name: "Labs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "启动正式验证任务" })).toBeVisible();
  expect(labReads).toBeGreaterThan(0);
  expect(diagnosticsReads).toBeGreaterThan(0);

  await mkdir("output/playwright", { recursive: true });
  await page.screenshot({ path: "output/playwright/affordance-console-labs.png", fullPage: true });
  await page.getByRole("button", { name: "关闭 Labs", exact: true }).click();
  await page.screenshot({ path: "output/playwright/affordance-console-connected.png", fullPage: true });
});
