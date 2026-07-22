// Accessibility gate: axe-core on the primary surfaces; serious+critical fail.
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./_base";

for (const path of ["/dashboard/ipo2"]) {
  test(`a11y · ${path} has no serious/critical violations`, async ({ watched: page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"]).analyze();
    const bad = results.violations.filter(v => ["serious", "critical"].includes(v.impact ?? ""));
    const detail = bad.map(v => `${v.id}: ${v.nodes.slice(0, 8).map(n => n.target.join(" ")).join(" | ")}`).join("  ///  ");
    expect(bad.map(v => `${v.id}: ${v.help} (${v.nodes.length})`), `axe violations — ${detail}`).toEqual([]);
  });
}
