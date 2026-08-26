import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("operator shell is isolated from diagnostics", async ({ page, request }) => {
  let diagnosisReads = 0;
  page.on("request", (outgoing) => {
    if (outgoing.method() === "GET" && outgoing.url().endsWith("/diagnostics")) diagnosisReads += 1;
  });
  await request.post("http://127.0.0.1:8100/diagnostics", {
    data: {
      schema_version: "benchmark.v1",
      case_id: "bad-case-17",
      status: "failed",
      success: false,
      terminal_stage: "control",
      terminal_code: "no_progress",
      prompt_tokens: 900,
      completion_tokens: 100,
      model_latency_ms: 220,
      runtime_latency_ms: 410,
      no_progress_count: 2,
      complete_request_tokens: 850,
      effective_input_limit: 1000,
      trace: {
        schema_version: "trace.v1",
        case_id: "bad-case-17",
        steps: [
          { step: 1, stage: "policy", progress: true, provider_attempts: 1, evidence_refs: ["trace:1"] },
          { step: 2, stage: "control", abnormal: true, retries: 1, evidence_refs: ["trace:2"] },
        ],
      },
    },
  });

  await page.goto("/");
  await expect(page.getByTestId("viewer-unavailable")).toBeVisible();
  const composer = page.locator("textarea").first();
  await expect(composer).toBeVisible();
  await composer.fill("Choose an option");
  await composer.press("Enter");
  await expect(page.getByTestId("pending-question")).toContainText("Which option");
  await composer.fill("The second one");
  await composer.press("Enter");
  await expect(page.getByTestId("confirmation-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Approve action" }).click();
  await expect(page.getByTestId("completion")).toContainText("Contract demo completed");
  await expect(page.getByTestId("diagnosis")).toHaveCount(0);
  expect(diagnosisReads).toBe(0);
  await page.goto("/diagnostics");
  await expect(page.getByTestId("diagnosis")).toContainText("bad-case-17");
  expect(diagnosisReads).toBeGreaterThan(0);
  await mkdir("output/playwright", { recursive: true });
  await page.screenshot({ path: "output/playwright/diagnostics-workbench.png", fullPage: true });
  await page.goto("/");
  await expect(page.getByText("takeover unsupported")).toBeVisible();
  await page.screenshot({ path: "output/playwright/interaction-shell.png", fullPage: true });
});
