import { join } from "node:path";

export const name = "orbit-skills";
export const inject = ["skills"];

export async function apply(ctx: unknown): Promise<void> {
  // The dsh host supplies its own provider; Orbit does not bundle a second runtime.
  const providerModule = "@deepseek-ai/dsh-skill-filesystem";
  const provider = await import(providerModule);
  provider.apply(ctx, {
    providerName: "orbit",
    includeDefaultRoots: false,
    bundledSkillDir: join(import.meta.dirname, "skills"),
    watch: false,
  });
}
