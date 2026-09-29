// Browser acceptance uses synthetic persisted batches and real HTTP/Records APIs.
const { spawn } = require("node:child_process");
const { createInterface } = require("node:readline");
const assert = require("node:assert/strict");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
(async () => {
  const server = spawn(
    "uv",
    ["run", "--locked", "python", "tests/web/benchmark_fixture.py"],
    { stdio: ["ignore", "pipe", "inherit"] },
  );
  let browser;
  try {
    const info = await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("fixture startup timeout")),
        20000,
      );
      createInterface({ input: server.stdout }).once("line", (line) => {
        clearTimeout(timer);
        resolve(JSON.parse(line));
      });
      server.once("exit", (code) =>
        reject(new Error(`fixture exited ${code}`)),
      );
    });
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
      args: ["--no-sandbox"],
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      permissions: ["clipboard-read", "clipboard-write"],
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors = [],
      bodies = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("response", async (r) => {
      if (r.url().includes("/api/"))
        try {
          bodies.push(await r.text());
        } catch {}
    });
    const base = `http://127.0.0.1:${info.port}`;
    await page.goto(`${base}/#benchmarks`);
    await page
      .getByLabel("访问令牌", { exact: true })
      .fill("benchmark-browser-fixture-token-123456789");
    await page.getByRole("button", { name: "连接控制台" }).click();
    // A pasted login URL in an existing tab is hash navigation, not an App remount.
    await page.evaluate(() => {
      window.loginNavigationMarker = "same-document";
    });
    await page.goto(`${base}/#token=benchmark-browser-fixture-token-123456789`);
    await page.waitForURL(`${base}/#benchmarks`);
    assert.equal(
      await page.evaluate(() => window.loginNavigationMarker),
      "same-document",
    );
    await page.getByRole("link", { name: "revised", exact: true }).waitFor();
    // Simulate a rotated token using an explicit HTTP test double, then restore the real fixture token.
    const rotated = "rotated-browser-fixture-token-123456789";
    const seenAuth = [];
    await page.route("**/api/v1/benchmarks/workspace", async (route) => {
      seenAuth.push(route.request().headers().authorization);
      await route.fulfill({ json: { batches: [], errors: [], settings: {} } });
    });
    await page.goto(`${base}/#token=${rotated}`);
    await page.waitForURL(`${base}/#benchmarks`);
    await page.waitForFunction(
      (expected) => sessionStorage.getItem("console-token") === expected,
      rotated,
    );
    const tokenRefreshResponse = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/v1/benchmarks/workspace") &&
        r.request().headers().authorization === `Bearer ${rotated}`,
    );
    await page.getByRole("button", { name: "刷新结果", exact: true }).click();
    await tokenRefreshResponse;
    assert(seenAuth.includes(`Bearer ${rotated}`));
    await page.unroute("**/api/v1/benchmarks/workspace");
    await page.getByRole("button", { name: "退出连接", exact: true }).click();
    await page.getByRole("heading", { name: "连接你的研究空间" }).waitFor();
    await page.goto(`${base}/#token=benchmark-browser-fixture-token-123456789`);
    await page.waitForURL(`${base}/#benchmarks`);
    await page.getByRole("link", { name: "revised", exact: true }).waitFor();
    await page.goto(`${base}/#does-not-exist`);
    await page
      .getByRole("heading", { name: "页面不存在", exact: true })
      .waitFor();
    await page.getByRole("link", { name: "返回实验列表", exact: true }).click();
    await page.getByRole("link", { name: "revised", exact: true }).click();
    await page
      .getByRole("heading", { name: "任务结果", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "跳到主要内容" }).focus();
    await page.keyboard.press("Enter");
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "main-content",
    );
    assert.equal(
      await page.locator(".bench-result-table tbody tr").count(),
      20,
    );
    const fifth = await page
      .locator(".bench-result-table tbody tr")
      .nth(4)
      .boundingBox();
    assert(
      fifth.y + fifth.height < 900,
      `five tasks should be visible in the first desktop screen: ${JSON.stringify(fifth)}`,
    );
    let overviewReads = 0;
    page.on("request", (r) => {
      if (r.url().endsWith("/api/v1/benchmarks/workspace")) overviewReads++;
    });
    await page.waitForTimeout(5300);
    assert.equal(overviewReads, 0, "completed overview should stop polling");
    await page.getByRole("button", { name: "下一页任务" }).click();
    await page.getByRole("button", { name: "下一页任务" }).click();
    await page.getByRole("link", { name: "task-059", exact: true }).waitFor();
    await page.getByRole("link", { name: "task-059", exact: true }).click();
    const savedScroll = Number(
      await page.evaluate(
        (batch) => sessionStorage.getItem(`bench-scroll-${batch}`),
        info.right,
      ),
    );
    await page
      .getByRole("heading", { name: "评分结果", exact: true })
      .waitFor();
    await page
      .getByRole("link", { name: "← 返回批次结果", exact: true })
      .click();
    assert(page.url().includes("page=2"));
    assert(
      Math.abs((await page.evaluate(() => scrollY)) - savedScroll) < 2,
      "return should restore scroll position",
    );
    await page.getByRole("link", { name: "task-059", exact: true }).waitFor();
    await page.getByLabel("搜索任务", { exact: true }).fill("task-000");
    await page.getByRole("link", { name: "task-000", exact: true }).waitFor();
    await page.reload();
    assert.equal(
      await page.getByLabel("搜索任务", { exact: true }).inputValue(),
      "task-000",
    );
    assert.equal(await page.locator(".bench-result-table tbody tr").count(), 1);
    await page.getByRole("link", { name: "task-000", exact: true }).click();
    await page
      .getByRole("heading", { name: "评分结果", exact: true })
      .waitFor();
    const refreshed = page.waitForResponse(
      (r) => r.url().endsWith("/detail") && r.status() === 200,
    );
    await page.getByRole("button", { name: "刷新任务", exact: true }).click();
    await refreshed;
    await page.getByRole("button", { name: "Agent 轨迹", exact: true }).click();
    await page.getByLabel("搜索轨迹", { exact: true }).waitFor();
    await page
      .getByRole("link", { name: "← 返回批次结果", exact: true })
      .click();
    assert.equal(
      await page.getByLabel("搜索任务", { exact: true }).inputValue(),
      "task-000",
    );
    await page.getByRole("link", { name: "实验笔记", exact: true }).click();
    await page.getByText("实验名称、说明与标签", { exact: true }).click();
    await page.getByLabel("实验名称", { exact: true }).fill("Prompt revision");
    await page
      .getByLabel("实验笔记", { exact: true })
      .fill("Improved output format; verify on another seed.");
    await page.getByRole("button", { name: "保存笔记" }).click();
    await page.getByRole("status").filter({ hasText: "已保存" }).waitFor();
    await page.reload();
    await page
      .getByRole("heading", { name: "Prompt revision", exact: true })
      .waitFor();
    await page.getByRole("link", { name: "实验比较", exact: true }).click();
    await page.getByRole("button", { name: "导出对比 CSV" }).waitFor();
    const csvDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出对比 CSV" }).click();
    assert.equal(
      (await csvDownload).suggestedFilename(),
      "benchmark-comparison.csv",
    );
    await page.getByText("同任务集的历史均分", { exact: true }).click();
    const chartDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出图表", exact: true }).click();
    assert.equal(
      (await chartDownload).suggestedFilename(),
      "benchmark-trend.svg",
    );
    await page.screenshot({
      path: "/tmp/workbench-comparison-20260928.png",
      fullPage: true,
    });
    await page.getByLabel("搜索对比任务").fill("task-000");
    await page.getByRole("link", { name: "并排查看轨迹" }).click();
    await page
      .getByRole("heading", { name: "基线实验", exact: true })
      .waitFor();
    await page.getByLabel("搜索轨迹", { exact: true }).last().waitFor();
    assert.equal(await page.getByLabel("搜索轨迹", { exact: true }).count(), 2);
    await page
      .getByLabel("搜索轨迹", { exact: true })
      .last()
      .fill("DEEP_ERROR");
    await page
      .getByText("DEEP_ERROR: missing column", { exact: true })
      .waitFor();
    await page.getByRole("button", { name: "复制步骤链接" }).last().click();
    await page.goto(await page.evaluate(() => navigator.clipboard.readText()));
    await page
      .getByText("DEEP_ERROR: missing column", { exact: true })
      .waitFor();
    await page.getByRole("button", { name: "文件与评分证据" }).last().click();
    await page.getByLabel("搜索证据文件").fill("outputs/score.json");
    await page.getByRole("button", { name: "预览", exact: true }).click();
    await page.getByText('"score": 0', { exact: false }).waitFor();
    const fileDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载", exact: true }).click();
    assert.equal((await fileDownload).suggestedFilename(), "score.json");
    await page.screenshot({
      path: "/tmp/workbench-evidence-20260928.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    if (
      !(await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ))
    ) {
      console.error(
        await page.evaluate(() =>
          [...document.querySelectorAll("body *")]
            .filter((el) => el.getBoundingClientRect().right > innerWidth + 1)
            .slice(0, 20)
            .map((el) => ({
              tag: el.tagName,
              cls: el.className,
              width: el.getBoundingClientRect().width,
              right: el.getBoundingClientRect().right,
            })),
        ),
      );
      await page.screenshot({
        path: "/tmp/workbench-overflow.png",
        fullPage: true,
      });
    }
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    );
    await page.goto(`${base}/#benchmarks`);
    await page.getByText("登记已有批次", { exact: true }).click();
    await page.getByLabel("批次目录", { exact: true }).fill(info.third);
    await page.getByRole("button", { name: "登记批次", exact: true }).click();
    await page
      .getByRole("heading", { name: "incomplete", exact: true })
      .waitFor();
    await page.getByLabel("结果筛选").selectOption("unscored");
    await page
      .getByRole("status")
      .filter({ hasText: "2 / 60 个任务" })
      .waitFor();
    await page.screenshot({
      path: "/tmp/workbench-mobile-20260928.png",
      fullPage: true,
    });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    );
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`${base}/#benchmarks/workspace?batch=${info.right}`);
    await page
      .getByRole("link", { name: "1 题评分需要复核", exact: true })
      .click();
    await page
      .getByRole("status")
      .filter({ hasText: "1 / 60 个任务" })
      .waitFor();
    await page.getByRole("link", { name: "task-000", exact: true }).click();
    await page.getByText("额度耗尽中断", { exact: false }).first().waitFor();
    await page.getByRole("link", { name: "评分原始证据", exact: true }).click();
    assert.equal(
      await page.getByLabel("搜索证据文件").inputValue(),
      "outputs/benchflow_score.json",
    );
    await page.getByRole("button", { name: "预览", exact: true }).click();
    await page
      .locator(".bench-preview")
      .getByText("evaluator_unavailable", { exact: false })
      .waitFor();
    const response = await page.request.get(
      `${base}/api/v1/benchmarks/workspace/${info.right}`,
      {
        headers: {
          Authorization: "Bearer benchmark-browser-fixture-token-123456789",
        },
      },
    );
    const detail = await response.json();
    const review = {
      schema_version: 1,
      snapshot: detail.review_snapshot,
      title: "Synthetic evidence review",
      author: "Fixture reviewer",
      summary: "Observed issue; method hypotheses remain untested.",
      report: "# Full report\n\n<script>window.reviewInjected=true</script>",
      cases: [
        {
          run_id: info.run,
          observation: "Saved numeric score",
          interpretation: "Do not infer method quality",
          next: "Check the evaluator first",
          evidence: [
            { label: "评分文件", member: "outputs/benchflow_score.json" },
            { label: "关键步骤 57", step: 57 },
          ],
        },
      ],
    };
    await page.goto(`${base}/#benchmarks/workspace?batch=${info.right}`);
    await page.getByText("导入研究复盘", { exact: true }).click();
    await page
      .getByLabel("选择复盘 JSON")
      .setInputFiles({
        name: "review.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(review)),
      });
    await page.getByText("研究复盘 · 1 个重点案例", { exact: true }).click();
    await page
      .getByText("Observed issue; method hypotheses remain untested.", {
        exact: true,
      })
      .waitFor();
    await page.getByRole("button", { name: "查看完整复盘报告" }).click();
    await page
      .locator(".review-report")
      .getByText("<script>", { exact: false })
      .waitFor();
    assert.equal(await page.evaluate(() => window.reviewInjected), undefined);
    const reportDownload = page.waitForEvent("download");
    await page.getByRole("button", { name: "下载完整报告" }).click();
    assert.equal(
      (await reportDownload).suggestedFilename(),
      "research-review.md",
    );
    await page.goto(
      `${base}/#benchmarks/workspace?batch=${info.right}&run=${info.run}`,
    );
    await page
      .getByText("Do not infer method quality", { exact: false })
      .waitFor();
    await page.getByRole("link", { name: "关键步骤 57" }).click();
    await page
      .getByText("DEEP_ERROR: missing column", { exact: true })
      .waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(
      `${base}/#benchmarks/workspace?batch=${info.right}&run=${info.run}`,
    );
    await page
      .getByText("Check the evaluator first", { exact: false })
      .waitFor();
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.screenshot({
      path: "/tmp/review-mobile-20260928.png",
      fullPage: true,
    });
    assert(!bodies.join("\n").includes("PRIVATE_NATIVE_SENTINEL"));
    assert.equal(errors.length, 0, errors.join("\n"));
    console.log(
      "PASS: list/detail, first-screen density, 60 tasks, URL filters/pagination, back/reload, stopped polling, notes, comparison/exports, trace deep links, files, registration, missing scores, health filters, review upload/report/evidence links, escaped HTML, mobile.",
    );
  } finally {
    await browser?.close();
    server.kill("SIGTERM");
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
