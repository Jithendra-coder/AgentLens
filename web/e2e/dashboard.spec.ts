import { expect, test } from "@playwright/test";

test("dashboard navigation exposes the M11 surfaces", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Trace volume", { exact: true }).first()).toBeVisible();
  await expect(page.locator('main a[href^="/traces/"]').first()).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link")).toHaveCount(8);
  await page.getByRole("link", { name: "Traces" }).click();
  await expect(page.getByRole("heading", { name: "Traces" })).toBeVisible();
  await page.goto("/evaluations");
  await expect(page.getByRole("heading", { name: "Evaluations" })).toBeVisible();
  await page.goto("/runtime");
  await expect(page.getByRole("heading", { name: "Runtime" })).toBeVisible();
});

test("M11 renders explicit blocking and advisory gate decisions", async ({ page }) => {
  const blockingDecisionId = process.env.AGENTLENS_M11_BLOCKING_DECISION_ID;
  const advisoryDecisionId = process.env.AGENTLENS_M11_ADVISORY_DECISION_ID;
  test.skip(
    !blockingDecisionId || !advisoryDecisionId,
    "Controlled PostgreSQL-backed M11 fixture decisions are required.",
  );

  await page.goto("/quality-gates");
  await expect(page.getByRole("heading", { name: "Quality Gates" })).toBeVisible();
  await page.goto(`/quality-gates/${blockingDecisionId}`);
  await expect(page.getByText("Gate", { exact: true })).toBeVisible();
  await expect(page.getByText("FAILED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Latency: BLOCKING FAILURE", { exact: true })).toBeVisible();

  await page.goto(`/quality-gates/${advisoryDecisionId}`);
  await expect(page.getByText("PASSED", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Advisories", { exact: true })).toBeVisible();
  await expect(page.getByText("Latency: FAILED", { exact: true })).toBeVisible();
});

test("M10 renders independent quality and latency outcomes", async ({ page }) => {
  const runId = process.env.AGENTLENS_M10_REGRESSION_RUN_ID;
  test.skip(!runId, "A controlled PostgreSQL-backed M10 fixture run is required.");
  await page.goto(`/regressions/${runId}`);
  await expect(page.getByText("Regression report", { exact: true })).toBeVisible();
  await expect(page.getByText("replay.execution_success_rate", { exact: true })).toBeVisible();
  await expect(page.getByText("trace.duration_ms.p95", { exact: true })).toBeVisible();
  await expect(page.getByText("improved", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("regressed", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("violated", { exact: true }).first()).toBeVisible();
});

test("M9 creates a dataset, runs a replay, and opens its trace", async ({ page }) => {
  const datasetName = `browser-m9-${Date.now()}`;

  await page.goto("/datasets");
  await page.getByLabel("Name").fill(datasetName);
  await page.getByLabel("Description").fill("Controlled browser smoke dataset");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByText("Dataset created.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: datasetName }).click();

  await page.getByRole("button", { name: "New draft version" }).click();
  await expect(page.getByText("Draft version created.", { exact: true })).toBeVisible();
  const versionLink = page.getByRole("link", { name: "v1" });
  const createdVersionHref = await versionLink.getAttribute("href");
  const createdVersionId = createdVersionHref?.split("/").pop();
  expect(createdVersionId).toBeTruthy();
  await versionLink.click();
  await page.getByLabel("Name").fill("browser case");
  await page.getByLabel("Input JSON").fill('{"prompt":"hello from chromium"}');
  await page.getByRole("button", { name: "Add case", exact: true }).click();
  await expect(page.getByText("Case added.", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Finalize immutable version" }).click();
  await expect(page.getByText("Version finalized and immutable.", { exact: true })).toBeVisible();

  await page.goto("/replays");
  const versionSelect = page.getByLabel("Finalized dataset version");
  await expect(versionSelect.locator(`option[value="${createdVersionId}"]`)).toBeAttached();
  await versionSelect.selectOption(createdVersionId!);
  await page.getByRole("button", { name: "Start replay" }).click();
  await expect(page.getByRole("status")).toHaveText("Replay queued.");
  const runLink = page.locator('.main a[href^="/replays/"]').first();
  await expect(runLink).toBeVisible();
  await runLink.click();

  let completed = false;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await page.getByRole("button", { name: "Refresh" }).click();
    if (await page.getByText("succeeded", { exact: true }).count()) {
      completed = true;
      break;
    }
    await page.waitForTimeout(500);
  }
  expect(completed).toBe(true);
  await page.getByRole("link", { name: "Open trace" }).click();
  await expect(page.getByText("Trace detail", { exact: true })).toBeVisible();
});
