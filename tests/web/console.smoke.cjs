// Optional browser check; uses externally installed Playwright, no production fixtures.
const { spawn } = require("node:child_process");
const { createInterface } = require("node:readline");
const assert = require("node:assert/strict");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");

(async () => {
  const server = spawn("uv", ["run", "--locked", "python", "tests/web/serve_fixture.py"], { stdio: ["ignore", "pipe", "inherit"] });
  let browser;
  try {
    const port = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("fixture server startup timeout")), 15000);
      createInterface({ input: server.stdout }).once("line", (line) => { clearTimeout(timer); resolve(JSON.parse(line).port); });
      server.once("exit", (code) => reject(new Error(`server exited ${code}`)));
    });
    browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--no-sandbox"] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 980 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const responseBodies = [];
    page.on("response", async (response) => {
      if (response.url().includes("/api/")) { try { responseBodies.push(await response.text()); } catch {} }
    });
    const base = `http://127.0.0.1:${port}`;
    await page.goto(`${base}/#token=browser-fixture-only-not-a-production-secret`);
    await page.getByRole("heading", { name: "总览", exact: true }).waitFor();
    assert(!page.url().includes("token="));
    await page.getByRole("link", { name: "科研项目", exact: true }).click();
    await page.getByRole("button", { name: "＋ 新建项目" }).click();
    await page.getByLabel("项目名称", { exact: true }).fill("浏览器验证项目");
    await page.getByLabel("研究目标").fill("Fixture only: exercise project persistence and associations");
    await page.getByLabel("里程碑标题").fill("完成训练");
    await page.getByRole("button", { name: "添加里程碑" }).click();
    await page.getByLabel("fixture-run", { exact: true }).check();
    await page.getByLabel("example-file-result", { exact: true }).check();
    await page.getByRole("button", { name: "保存项目" }).click();
    await page.getByRole("heading", { name: "浏览器验证项目", exact: true }).waitFor();
    await page.reload();
    await page.getByRole("heading", { name: "浏览器验证项目", exact: true }).waitFor();
    await page.getByRole("button", { name: "编辑项目" }).click();
    await page.getByLabel("完成训练", { exact: true }).check();
    await page.getByRole("button", { name: "保存项目" }).click();
    await page.getByText("里程碑 1 / 1", { exact: true }).waitFor();
    await page.getByRole("link", { name: "fixture-run ↗", exact: true }).click();
    await page.getByText("Browser fixture: training finished", { exact: true }).waitFor();
    await page.getByText("fixture-result.txt", { exact: true }).waitFor();
    await page.getByRole("link", { name: "资源", exact: true }).click();
    await page.getByRole("heading", { name: "CPU 使用率", exact: true }).waitFor();
    await page.screenshot({ path: "/tmp/agent-infra-web-resources.png", fullPage: true });
    await page.getByRole("link", { name: "任务", exact: true }).click();
    await page.getByRole("heading", { name: "example-file-result", exact: true }).waitFor();
    for (const name of ["Agents", "记录", "设置", "总览"]) {
      await page.getByRole("link", { name, exact: true }).click();
      await page.getByRole("heading", { name, exact: true }).waitFor();
    }
    await page.screenshot({ path: "/tmp/agent-infra-web-overview.png", fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "/tmp/agent-infra-web-mobile.png", fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    assert.equal(errors.length, 0, errors.join("\n"));
    assert(!responseBodies.join("\n").includes("EVALUATOR_SECRET_SENTINEL"));
    assert(!responseBodies.join("\n").includes("private/expected.txt"));
    await page.getByRole("button", { name: "退出连接" }).click();
    await page.getByRole("heading", { name: "连接你的研究空间" }).waitFor();
    assert.equal(await page.evaluate(() => sessionStorage.getItem("console-token")), null);
    console.log("Browser smoke passed: project create/edit/reload, task/run links, trace/artifact, real host sampling, navigation, mobile width, logout, no private fixture data or page errors.");
  } finally {
    await browser?.close();
    server.kill("SIGTERM");
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
