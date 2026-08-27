import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("operator shell is isolated from completed-run summaries", async ({ page }) => {
  let diagnosisReads = 0;
  const commandPaths: string[] = [];
  page.on("request", (outgoing) => {
    if (outgoing.method() === "GET" && outgoing.url().endsWith("/diagnostics")) diagnosisReads += 1;
    if (outgoing.method() === "POST" && outgoing.url().includes("/shell-api/sessions/")) {
      commandPaths.push(new URL(outgoing.url()).pathname);
    }
  });
  await page.goto("/");
  await expect(page.getByTestId("surface-unavailable")).toBeVisible();
  const composer = page.getByRole("textbox", { name: "Task command" });
  await expect(composer).toBeVisible();
  await composer.fill("Choose an option");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("pending-question")).toContainText("Which option");
  await expect(page.getByText("live", { exact: true })).toBeVisible();
  await composer.fill("The second one");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("confirmation-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Approve action" }).click();
  await expect(page.getByTestId("completion")).toContainText("Contract demo completed");
  expect(commandPaths).toHaveLength(3);
  expect(commandPaths.every((path) => path.endsWith("/commands"))).toBe(true);
  await expect(page.getByTestId("completed-run-summary")).toHaveCount(0);
  expect(diagnosisReads).toBe(0);
  await page.goto("/diagnostics");
  await expect(page.getByText("No configured completed runs.")).toBeVisible();
  expect(diagnosisReads).toBeGreaterThan(0);
  await mkdir("output/playwright", { recursive: true });
  await page.screenshot({ path: "output/playwright/diagnostics-workbench.png", fullPage: true });
  await page.goto("/");
  await expect(page.getByText("Surface unavailable")).toBeVisible();
  await page.screenshot({ path: "output/playwright/interaction-shell.png", fullPage: true });
});
