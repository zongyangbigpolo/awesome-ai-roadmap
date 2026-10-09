import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { localPath, render, validateJob } from "./render.mjs";


test("renderer rejects remote resources and unsupported languages", () => {
  assert.throws(() => localPath("http://localhost/%2e%2e%2fsecret"), /escapes/);
  assert.throws(() => validateJob({
    key: "a".repeat(64), kind: "mermaid",
    source: 'flowchart LR\n A["<img src=\\"https://example.org/image.png\\">"]',
  }), /explicit static conversion/);
  assert.throws(() => validateJob({
    key: "a".repeat(64), kind: "inline", source: "x", language: "fr",
  }), /invalid render job/);
});

test("real offline bilingual diagrams and math, language-safe cache, and hard math errors", async () => {
  const scratch = await fs.mkdtemp(path.join(os.tmpdir(), "epub-render-test-"));
  try {
    const request = path.join(scratch, "jobs.json");
    const jobs = [
      { kind: "mermaid", source: 'flowchart LR\n A["中文：检索"] --> B["生成"]', language: "zh-CN" },
      { kind: "inline", source: "x_i^2", language: "zh-CN" },
      { kind: "display", source: "\\frac{e^{z_i}}{\\sum_j e^{z_j}}", language: "zh-CN" },
      { kind: "mermaid", source: 'flowchart LR\n A["Retrieve supporting documents"] --> B["Generate a grounded answer"]', language: "en" },
      { kind: "inline", source: "x_i^2", language: "en" },
      { kind: "display", source: "\\frac{e^{z_i}}{\\sum_j e^{z_j}}", language: "en" },
    ].map((job) => ({ ...job, key: createHash("sha256").update(job.kind + "\0" + job.source).digest("hex") }));
    await fs.writeFile(request, JSON.stringify(jobs));
    const first = await render(request, scratch);
    assert.equal(first.results.length, 6);
    assert.equal(first.network_requests_blocked, 0);
    assert.equal(new Set(first.results.map((image) => image.file)).size, 6,
      "identical formulas in different languages must have separate cache entries");
    for (const image of first.results) {
      const png = await fs.readFile(path.join(scratch, image.file));
      assert.equal(png.subarray(1, 4).toString(), "PNG");
      assert.ok(["en", "zh-CN"].includes(image.language));
      assert.ok(image.width > 10 && image.height > 10);
      assert.deepEqual(image.tiles, [], "render only complete images, never cropped panels");
      if (image.kind !== "mermaid") {
        assert.equal(image.svgCount, 1, "capture exactly one rendered formula");
        assert.equal(image.mathmlCount, 0, "assistive MathML must not be visibly captured");
      }
    }
    assert.deepEqual(await render(request, scratch), first);
    await fs.writeFile(path.join(scratch, `${jobs[0].key}-${jobs[0].language}.json`), '{"truncated":');
    assert.deepEqual(await render(request, scratch), first);
    const invalid = { kind: "inline", source: "\\notARealCommand{x}", key: "a".repeat(64) };
    await fs.writeFile(request, JSON.stringify([invalid]));
    await assert.rejects(render(request, scratch), /Undefined control sequence|merror/);
  } finally {
    await fs.rm(scratch, { recursive: true, force: true });
  }
});

test("renderer detects subgraph titles overlapping nodes", async () => {
  const scratch = await fs.mkdtemp(path.join(os.tmpdir(), "epub-label-test-"));
  try {
    const jobs = [0, 30].map((bottom) => {
      const config = { flowchart: { nodeSpacing: 16, rankSpacing: 20,
        subGraphTitleMargin: { top: 4, bottom } } };
      const source = `%%{init: ${JSON.stringify(config)}}%%\nflowchart TB
subgraph G["Logical blocks"]
direction LR
A["Block 0"] --> B["Block 1"] --> C["Block 2"]
end
G --> D["Block table"]`;
      return { kind: "mermaid", language: "en", source,
        key: createHash("sha256").update(source).digest("hex") };
    });
    const request = path.join(scratch, "jobs.json");
    await fs.writeFile(request, JSON.stringify(jobs));
    const result = await render(request, scratch);
    assert.deepEqual(result.results[0].labelCollisions, [{ title: "Logical blocks", node: "Block 1" }]);
    assert.deepEqual(result.results[1].labelCollisions, []);
    assert.ok(result.results.every((image) => image.tiles.length === 0));
  } finally {
    await fs.rm(scratch, { recursive: true, force: true });
  }
});
