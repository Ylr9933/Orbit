import type { Command } from "commander";
import type { OrbitClient } from "../client/index.ts";
import type { NotifyEvent, NotifyTarget } from "../contracts/index.ts";
import type { Print } from "./auth.ts";

/** What the bot needs, pre-filled on the confirm page after scanning (when Feishu allows it). */
export const FEISHU_ADDONS = {
  scopes: {
    tenant: [
      "im:message",
      "im:message:send_as_bot",
      "im:message.p2p_msg:readonly",
      "im:message.group_at_msg:readonly",
    ],
  },
  events: { items: { tenant: ["im.message.receive_v1"] } },
};

export interface Registered {
  client_id: string;
  client_secret: string;
  user_info?: { open_id?: string; tenant_brand?: string };
}

export interface FeishuInitDeps {
  client: OrbitClient;
  /** The SDK's QR-code app registration (replaced in tests). */
  register(onQr: (url: string, expireIn: number) => void): Promise<Registered>;
  qr(url: string): string;
  /** Progress lines (stderr, so `--json` output stays clean). */
  say(line: string): void;
  sleep?(ms: number): Promise<void>;
}

export interface CheckResult {
  name: string;
  appId: string;
  users: number;
  connection: NonNullable<NotifyTarget["connection"]>;
  test: "sent" | "skipped" | string;
}

const console_ = (appId: string, page: string) => `https://open.feishu.cn/app/${appId}/${page}`;

/** Reconnect the bot, wait for its long connection and send a test card to the paired users. */
export async function checkFeishu(
  d: Omit<FeishuInitDeps, "register" | "qr">,
  name: string,
  waitMs = 30_000,
): Promise<CheckResult> {
  const sleep = d.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  await d.client.notifyReconnect(name);
  let t: NotifyTarget | undefined;
  for (let waited = 0; ; waited += 1000) {
    t = (await d.client.notifyList()).find((x) => x.name === name);
    if (t?.kind !== "feishu-app") throw new Error(`${name} is not a feishu-app target`);
    if (t.connection === "connected" || t.connection === "failed" || waited >= waitMs) break;
    await sleep(1000);
  }
  const appId = t.urlHint;
  const connection = t.connection ?? "stopped";
  if (connection === "connected") d.say("✓ long connection is up");
  else
    d.say(
      `✗ long connection ${connection}: in ${console_(appId, "event")} set the subscription mode to ` +
        `"persistent connection", add the event im.message.receive_v1, publish a version, then run ` +
        `\`orbit feishu check ${name}\``,
    );
  let test = "skipped";
  if (!t.users)
    d.say(
      `- nobody paired yet: message the bot in Feishu and run the \`orbit notify pair\` it replies with`,
    );
  else
    try {
      await d.client.notifyTest(name);
      test = "sent";
      d.say("✓ test card sent to you in Feishu");
    } catch (e) {
      test = (e as Error).message;
      d.say(
        `✗ test card failed (${test}); grant the bot permission to send messages in ` +
          `${console_(appId, "auth")}, publish a version, then run \`orbit feishu check ${name}\``,
      );
    }
  return { name, appId, users: t.users ?? 0, connection, test };
}

/** Create a Feishu app by scanning a QR code, save it as a target paired with the scanner, check it. */
export async function initFeishu(
  d: FeishuInitDeps,
  name: string,
  on: NotifyEvent[],
): Promise<CheckResult> {
  if ((await d.client.notifyList()).some((t) => t.name === name))
    throw new Error(
      `a target named ${name} exists; give another name or \`orbit notify rm ${name}\``,
    );
  const r = await d.register((url, expireIn) => {
    d.say(d.qr(url));
    d.say(
      `Scan with the Feishu app and confirm (valid ${Math.round(expireIn / 60)} min), or open:`,
    );
    d.say(url);
  });
  if (r.user_info?.tenant_brand === "lark")
    d.say("! this is a Lark (international) tenant; Orbit only talks to open.feishu.cn so far");
  const openId = r.user_info?.open_id;
  await d.client.notifyPut({
    name,
    kind: "feishu-app",
    appId: r.client_id,
    appSecret: r.client_secret,
    users: openId ? [openId] : [],
    on,
  });
  d.say(`✓ created app ${r.client_id}${openId ? " and paired it with you" : ""}`);
  return checkFeishu(d, name);
}

export function registerFeishu(
  program: Command,
  client: () => Promise<OrbitClient>,
  print: Print,
): void {
  const feishu = program
    .command("feishu")
    .description("a Feishu bot for your phone: run cards with curves, /gpu, /runs, /show");
  const say = (line: string) => console.error(line);
  const report = (r: CheckResult) =>
    `${r.name}: app ${r.appId}, ${r.users} paired, connection ${r.connection}, test ${r.test}`;

  feishu
    .command("init [name]")
    .description(
      "create a Feishu bot by scanning a QR code with the Feishu app; it is paired with you",
    )
    .option("--on <events>", "comma-separated: succeeded,failed,group", "succeeded,failed,group")
    .option("--app-name <name>", "app name shown in Feishu ({user} is the scanner's name)", "Orbit")
    .option("--json", "print JSON")
    .action(
      async (name: string | undefined, o: { on: string; appName: string; json?: boolean }) => {
        const { registerApp } = await import("@larksuiteoapi/node-sdk");
        const { renderUnicodeCompact } = await import("uqr");
        const r = await initFeishu(
          {
            client: await client(),
            say,
            qr: (url) => renderUnicodeCompact(url),
            register: (onQr) =>
              registerApp({
                createOnly: true,
                source: "orbit",
                appPreset: { name: o.appName, desc: "Orbit experiment notifications and status" },
                addons: FEISHU_ADDONS,
                onQRCodeReady: ({ url, expireIn }) => onQr(url, expireIn),
              }),
          },
          name ?? "feishu",
          o.on.split(",").filter(Boolean) as NotifyEvent[],
        );
        print(o.json, r, () => report(r));
      },
    );

  feishu
    .command("check <name>")
    .description("reconnect a Feishu bot (e.g. after changing its settings) and send a test card")
    .option("--json", "print JSON")
    .action(async (name: string, o: { json?: boolean }) => {
      const r = await checkFeishu({ client: await client(), say }, name);
      print(o.json, r, () => report(r));
      if (r.connection !== "connected" || (r.test !== "sent" && r.test !== "skipped"))
        process.exitCode = 1;
    });
}
