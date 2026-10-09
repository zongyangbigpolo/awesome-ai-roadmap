import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer";

const directory = path.dirname(fileURLToPath(import.meta.url));
const dependencies = path.join(directory, "node_modules");
const sha256 = (data) => createHash("sha256").update(data).digest("hex");

export function validateJob(job) {
  if (!/^[a-f0-9]{64}$/.test(job.key) || !["mermaid", "inline", "display"].includes(job.kind) ||
      typeof job.source !== "string" || !["en", "zh-CN"].includes(job.language ?? "en")) {
    throw new Error("invalid render job");
  }
  if (job.kind === "mermaid" &&
      /<\s*(?:img|image|script|iframe)\b|\b(?:img|icon)\s*:|^\s*click\s/m.test(job.source)) {
    throw new Error("Mermaid images, icons and interactive links require explicit static conversion");
  }
}

export function localPath(url) {
  const target = path.resolve(dependencies, `.${decodeURIComponent(new URL(url).pathname)}`);
  if (!target.startsWith(dependencies + path.sep)) throw new Error("resource escapes dependencies");
  return target;
}

export async function render(requestPath, outputDirectory) {
  if (process.platform === "linux" && process.arch !== "x64") {
    throw new Error("Pinned Chromium export supports Linux x64 only; use an x64 runner or macOS.");
  }
  const jobs = JSON.parse(await fs.readFile(requestPath, "utf8"));
  jobs.forEach(validateJob);
  await fs.mkdir(outputDirectory, { recursive: true });
  // Cache keys include the renderer and lockfile, not just the expression.
  const version = sha256(Buffer.concat([
    await fs.readFile(fileURLToPath(import.meta.url)),
    await fs.readFile(path.join(directory, "package-lock.json")),
  ]));
  const failures = [];
  const server = http.createServer(async (request, response) => {
    try {
      const target = localPath(`http://localhost${request.url}`);
      const mime = { ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".woff2": "font/woff2" };
      response.setHeader("Access-Control-Allow-Origin", "*");
      response.setHeader("Content-Type", mime[path.extname(target)] || "application/octet-stream");
      response.end(await fs.readFile(target));
    } catch (error) {
      failures.push(`local resource: ${request.url}: ${error.message}`);
      response.writeHead(404).end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: true,
      // Opt-in only for disposable CI runners that cannot use the Chromium sandbox.
      args: process.env.EPUB_NO_SANDBOX === "1" ? ["--no-sandbox"] : [],
    });
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 1000, deviceScaleFactor: 2 });
    const origin = `http://127.0.0.1:${server.address().port}`;
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (new URL(request.url()).origin === origin && request.method() === "GET") {
        request.continue();
      } else {
        failures.push(`network request prohibited: ${request.url()}`);
        request.abort();
      }
    });
    page.on("pageerror", (error) => failures.push(error.message));
    await page.setContent(`<!doctype html><html lang="en"><head>
      <link rel="stylesheet" href="${origin}/@fontsource/noto-sans-sc/400.css">
      <style>
        body { margin:0; background:white; color:#111; font:20px "Noto Sans SC",sans-serif; }
        #stage { display:inline-block; padding:12px; background:white; }
        #stage svg { max-width:none !important; overflow:visible; }
        mjx-container { margin:0 !important; }
      </style></head><body><div id="stage"></div></body></html>`);
    await page.evaluate(() => {
      window.MathJax = {
        startup: { typeset: false },
        loader: { load: [] },
        tex: {
          packages: { "[-]": ["noerrors", "noundefined", "autoload", "require"] },
          formatError: (_jax, error) => { throw new Error(error.message); },
        },
        svg: { fontCache: "local" },
      };
    });
    await page.addScriptTag({ url: `${origin}/mathjax/es5/tex-svg.js` });
    await page.evaluate(async (origin) => {
      await window.MathJax.startup.promise;
      window.mermaid = (await import(`${origin}/mermaid/dist/mermaid.esm.min.mjs`)).default;
      window.mermaid.initialize({
        startOnLoad: false, securityLevel: "strict", theme: "default",
        fontFamily: '"Noto Sans SC", sans-serif',
        themeVariables: { fontFamily: '"Noto Sans SC", sans-serif', fontSize: "18px" },
        flowchart: { useMaxWidth: false, htmlLabels: true },
        sequence: { useMaxWidth: false },
      });
    }, origin);
    const results = [];
    for (const [index, job] of jobs.entries()) {
      const language = job.language ?? "en";
      const cacheKey = `${job.key}-${language}`;
      const cacheFile = path.join(outputDirectory, `${cacheKey}.json`);
      let cached;
      try {
        cached = JSON.parse(await fs.readFile(cacheFile, "utf8"));
      } catch (error) {
        if (error instanceof SyntaxError) {
          console.error(`Regenerating malformed render cache: ${cacheFile}`);
        } else if (error.code !== "ENOENT") {
          throw error;
        }
      }
      if (cached?.version === version && cached.language === language) {
        const images = [cached, ...cached.tiles];
        let intact = true;
        for (const image of images) {
          try {
            intact &&= sha256(await fs.readFile(path.join(outputDirectory, image.file))) === image.sha256;
          } catch (error) {
            if (error.code !== "ENOENT") throw error;
            intact = false;
          }
        }
        if (intact) {
          results.push(cached);
          continue;
        }
      }
      let geometry;
      try {
        geometry = await page.evaluate(async (job) => {
          document.documentElement.lang = job.language ?? "en";
          const stage = document.getElementById("stage");
          stage.replaceChildren();
          stage.style.padding = job.kind === "inline" ? "2px" : "12px";
          // Load glyphs before Mermaid measures labels (not after it lays out boxes).
          await document.fonts.load('20px "Noto Sans SC"', job.source);
          if (job.kind === "mermaid") {
            stage.innerHTML = (await window.mermaid.render("diagram", job.source)).svg;
            const svg = stage.querySelector("svg");
            const box = svg.viewBox.baseVal;
            if (!box.width || !box.height) throw new Error("diagram has no dimensions");
            svg.setAttribute("width", box.width);
            svg.setAttribute("height", box.height);
          } else {
            const math = await window.MathJax.tex2svgPromise(job.source, {
              display: job.kind === "display",
            });
            if (math.querySelector('[data-mml-node="merror"], merror, .mjx-merror')) {
              throw new Error("MathJax merror");
            }
            // tex2svg also carries assistive MathML. Chromium can visibly draw it
            // a second time without MathJax's document stylesheet; capture only SVG.
            const svg = math.querySelector("svg");
            if (!svg) throw new Error("MathJax did not produce an SVG");
            stage.appendChild(svg);
          }
          await document.fonts.ready;
          const rectangle = stage.getBoundingClientRect();
          const labelCollisions = [];
          if (job.kind === "mermaid") {
            for (const label of stage.querySelectorAll(".cluster-label")) {
              const title = label.getBoundingClientRect();
              for (const node of stage.querySelectorAll("g.node")) {
                const box = node.getBoundingClientRect();
                if (Math.min(title.right, box.right) - Math.max(title.left, box.left) > 1 &&
                    Math.min(title.bottom, box.bottom) - Math.max(title.top, box.top) > 1) {
                  labelCollisions.push({ title: label.textContent.trim(), node: node.textContent.trim() });
                }
              }
            }
          }
          return {
            width: Math.ceil(rectangle.width), height: Math.ceil(rectangle.height),
            svgCount: stage.querySelectorAll("svg").length,
            mathmlCount: stage.querySelectorAll("math").length,
            labelCollisions,
          };
        }, job);
      } catch (error) {
        throw new Error(`${job.kind} ${job.key}: ${error.message}\n${job.source.slice(0, 300)}`);
      }
      if (failures.length) throw new Error(failures.join("\n"));
      if (geometry.width > 16000 || geometry.height > 16000 || geometry.width * geometry.height > 40_000_000) {
        throw new Error(`${job.key}: image too large; revise diagram layout explicitly`);
      }
      const file = `${cacheKey}.png`;
      const screenshot = await page.screenshot({
        path: path.join(outputDirectory, file),
        clip: { x: 0, y: 0, width: geometry.width, height: geometry.height },
        captureBeyondViewport: true,
      });
      const result = {
        key: job.key, kind: job.kind, language, version, file, ...geometry,
        sha256: sha256(screenshot), tiles: [],
      };
      const pendingCache = `${cacheFile}.${process.pid}.tmp`;
      await fs.writeFile(pendingCache, JSON.stringify(result));
      await fs.rename(pendingCache, cacheFile);
      results.push(result);
      if ((index + 1) % 50 === 0) console.error(`rendered ${index + 1}/${jobs.length}`);
    }
    if (failures.length) throw new Error(failures.join("\n"));
    return { version, results, network_requests_blocked: failures.length };
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [, , request, output, receipt] = process.argv;
    if (!request || !output || !receipt) throw new Error("usage: node render.mjs jobs.json cache-directory receipt.json");
    await fs.writeFile(receipt, JSON.stringify(await render(request, output), null, 2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
