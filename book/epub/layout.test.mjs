import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import puppeteer from "puppeteer";

const directory = path.dirname(fileURLToPath(import.meta.url));
// node --test treats trailing flags as file selectors; select the edition with:
// EPUB_LANGUAGE=zh-CN npm run test:layout --prefix book/epub (default: en).
// Test-only tiny-book override: EPUB_FILE=/absolute/path/book.epub EPUB_LANGUAGE=en npm run test:layout --prefix book/epub.
const language = process.env.EPUB_LANGUAGE ?? "en";
assert.ok(["en", "zh-CN"].includes(language), `unsupported EPUB_LANGUAGE: ${language}`);
const fixture = process.env.EPUB_FILE !== undefined;
if (fixture) assert.ok(path.isAbsolute(process.env.EPUB_FILE), "EPUB_FILE must be an absolute path");
const epub = fixture ? process.env.EPUB_FILE
  : path.resolve(directory, `../${language}/generated/epub/ai-engineering-interview-${language}.epub`);
const requiredIds = fixture ? ["llm-01", "llm-02"] : ["llm-01", "llm-02", "llm-15", "agent-03"];

test(`actual ${language} EPUB at 375px and 16/24/32px: tables, math and code remain within the page`, async () => {
  const extracted = await fs.mkdtemp(path.join(os.tmpdir(), "epub-layout-"));
  let server;
  let browser;
  const measurements = [];
  try {
    execFileSync("python3", ["-m", "zipfile", "-e", epub, extracted]);
    server = http.createServer(async (request, response) => {
      const target = path.resolve(extracted, `.${decodeURIComponent(new URL(request.url, "http://localhost").pathname)}`);
      if (!target.startsWith(extracted + path.sep)) {
        response.writeHead(403).end();
        return;
      }
      try {
        const mime = { ".xhtml": "application/xhtml+xml", ".css": "text/css", ".png": "image/png" };
        response.setHeader("Content-Type", mime[path.extname(target)] || "application/octet-stream");
        response.end(await fs.readFile(target));
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
        response.writeHead(404).end();
      }
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await puppeteer.launch({
      headless: true,
      args: process.env.EPUB_NO_SANDBOX === "1" ? ["--no-sandbox"] : [],
    });
    const page = await browser.newPage();
    await page.setViewport({ width: 375, height: 812 });
    const packageLanguage = await page.evaluate((source) => new DOMParser()
      .parseFromString(source, "application/xml")
      .getElementsByTagNameNS("http://purl.org/dc/elements/1.1/", "language")[0]?.textContent,
    await fs.readFile(path.join(extracted, "EPUB/content.opf"), "utf8"));
    assert.equal(packageLanguage, language, "test the requested edition, never a fallback");
    const documents = await Promise.all((await fs.readdir(path.join(extracted, "EPUB/text")))
      .filter((file) => file.endsWith(".xhtml")).sort().map(async (file) => ({
        file: `EPUB/text/${file}`,
        source: await fs.readFile(path.join(extracted, "EPUB/text", file), "utf8"),
      })));
    const selected = await page.evaluate(({ documents, requiredIds }) => {
      const matches = Object.fromEntries(requiredIds.map((id) => [id, []]));
      for (const { file, source } of documents) {
        const document = new DOMParser().parseFromString(source, "application/xhtml+xml");
        if (document.querySelector("parsererror")) throw new Error(`invalid XHTML: ${file}`);
        for (const element of document.querySelectorAll("[id]")) {
          if (Object.hasOwn(matches, element.id)) matches[element.id].push(file);
        }
      }
      return requiredIds.map((id) => ({ id, files: matches[id] }));
    }, { documents, requiredIds });
    const chapters = selected.map(({ id, files }) => {
      assert.equal(files.length, 1, `required chapter ${id} must occur exactly once; found ${files.length}`);
      return { id, file: files[0] };
    });
    assert.equal(new Set(chapters.map((chapter) => chapter.file)).size, chapters.length,
      "required chapters must be separate XHTML documents");
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (new URL(request.url()).origin === origin) request.continue();
      else request.abort();
    });
    for (const { id: chapter, file } of chapters) {
      await page.goto(`${origin}/${file}`, { waitUntil: "networkidle0" });
      if (language === "en") {
        await page.evaluate(() => {
          // Exercise the packaged stylesheet without changing the manuscript or EPUB.
          const stress = document.createElementNS("http://www.w3.org/1999/xhtml", "section");
          stress.id = "english-layout-stress";
          for (const tag of ["p", "pre", "code"]) {
            const element = document.createElementNS(stress.namespaceURI, tag);
            element.textContent = "retrievalAugmentedGenerationConfiguration".repeat(12);
            stress.appendChild(element);
          }
          document.body.appendChild(stress);
        });
      }
      for (const fontSize of [16, 24, 32]) {
        const geometry = await page.evaluate(async (fontSize) => {
          document.body.style.fontSize = `${fontSize}px`;
          await document.fonts.ready;
          const formulas = Array.from(document.querySelectorAll("img.inline-math, img.display-math"));
          const sizes = formulas.map((image) => {
            const style = getComputedStyle(image);
            return {
              ratio: parseFloat(style.width) / parseFloat(style.height),
              naturalRatio: image.naturalWidth / image.naturalHeight,
              linked: image.parentElement.matches("a.formula-link"),
            };
          });
          return {
            language: document.documentElement.lang,
            xmlLanguage: document.documentElement.getAttributeNS("http://www.w3.org/XML/1998/namespace", "lang"),
            width: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            sizes,
            overflowingCode: Array.from(document.querySelectorAll("pre"))
              .filter((block) => block.scrollWidth > block.clientWidth + 1).length,
            clipped: Array.from(document.querySelectorAll("pre, table, td, .formula"))
              .filter((element) => ["hidden", "clip"].includes(getComputedStyle(element).overflowX)).length,
            longWordOverflow: Array.from(document.querySelectorAll("#english-layout-stress > *"))
              .filter((element) => element.scrollWidth > element.clientWidth + 1).length,
          };
        }, fontSize);
        assert.equal(geometry.language, language, `${chapter}: HTML language`);
        assert.equal(geometry.xmlLanguage, language, `${chapter}: XML language`);
        assert.ok(geometry.scrollWidth <= geometry.width + 1,
          `${chapter} font ${fontSize}: scrollWidth=${geometry.scrollWidth}, viewport=${geometry.width}`);
        assert.equal(geometry.overflowingCode, 0, `${chapter}: code wraps without truncation`);
        assert.equal(geometry.clipped, 0, `${chapter}: content is not hidden to fake a layout pass`);
        assert.equal(geometry.longWordOverflow, 0, `${chapter}: long English words and code wrap`);
        measurements.push({ chapter, file, fontSize, ...geometry });
        for (const image of geometry.sizes) {
          assert.ok(Math.abs(image.ratio / image.naturalRatio - 1) < 0.02, "formula must keep its aspect ratio");
          assert.ok(image.linked, "a constrained formula must open its complete image");
        }
      }
    }
    const wideChapter = chapters.find((chapter) => chapter.id === (fixture ? "llm-01" : "agent-03"));
    await page.goto(`${origin}/${wideChapter.file}`, { waitUntil: "networkidle0" });
    for (const width of [375, 768]) {
      await page.setViewport({ width, height: 1024 });
      const tables = await page.$$eval("table.wide-table", (tables) => tables.map((table) => ({
        labels: [...table.querySelectorAll(".cell-label")].map((label) => ({
          text: label.textContent, display: getComputedStyle(label).display,
          alignment: getComputedStyle(label).textAlign,
        })),
        cellWidths: [...table.querySelectorAll("tbody td")].map((cell) => cell.clientWidth),
        display: getComputedStyle(table).display,
      })));
      assert.ok(tables.length, "exercise real wide-table output");
      for (const table of tables) {
        assert.ok(table.labels.length >= 4);
        assert.ok(table.labels.every((label) => label.text.trim()));
        assert.equal(table.display, width === 375 ? "block" : "table");
        assert.ok(table.labels.every((label) => label.display === (width === 375 ? "block" : "none")));
        if (width === 375) assert.ok(table.cellWidths.every((cell) => cell >= 300),
          "wide-table values must use the available line rather than narrow columns");
        if (width === 375) assert.ok(table.labels.every((label) => label.alignment === "left"),
          "stacked fields do not inherit numeric-column alignment");
      }
    }
    await page.setViewport({ width: 375, height: 812 });
    const formulaChapter = chapters.find((chapter) => chapter.id === (fixture ? "llm-01" : "llm-15"));
    await page.goto(`${origin}/${formulaChapter.file}`, { waitUntil: "networkidle0" });
    const target = await page.$eval("a.formula-link", (link) => ({
      href: link.href, occurrence: link.closest(".formula").id,
    }));
    assert.match(target.occurrence, /^formula-\d+$/);
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle0" }),
      page.click("a.formula-link"),
    ]);
    assert.equal(page.url(), target.href);
    assert.equal(await page.$$eval("img.full-formula", (images) => images.length), 1);
    assert.equal(await page.evaluate(() => document.documentElement.lang), language);
    assert.equal(await page.$eval("body > a", (link) => link.textContent),
      language === "en" ? "Return to this formula in the text" : "返回正文中的此公式");
    const back = await page.$eval("body > a", (link) => link.href);
    assert.equal(back, `${origin}/${formulaChapter.file}#${target.occurrence}`);
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle0" }),
      page.click("body > a"),
    ]);
    assert.equal(page.url(), back);
    assert.ok(await page.evaluate(() => Boolean(document.getElementById(location.hash.slice(1)))));
    const figureDocuments = await Promise.all((await fs.readdir(path.join(extracted, "EPUB/figures")))
      .filter((file) => file.endsWith(".xhtml")).map(async (file) => ({
        file: `EPUB/figures/${file}`,
        source: await fs.readFile(path.join(extracted, "EPUB/figures", file), "utf8"),
      })));
    const diagramDocuments = [...documents, ...figureDocuments].filter(({ source }) =>
      /class="[^"]*\bdiagram\b/.test(source));
    const diagramMeasurements = [];
    for (const { file } of diagramDocuments) {
      await page.goto(`${origin}/${file}`, { waitUntil: "load" });
      for (const width of [375, 768]) {
        await page.setViewport({ width, height: 812 });
        const diagrams = await page.evaluate(async () => {
          await document.fonts.ready;
          return [...document.querySelectorAll("img.diagram")].map((image) => {
            const box = image.getBoundingClientRect();
            const style = getComputedStyle(image);
            const contentWidth = box.width - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            const contentHeight = box.height - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
            return {
              src: image.getAttribute("src"), width: box.width, height: box.height,
              nativeWidth: image.naturalWidth / 2, nativeHeight: image.naturalHeight / 2,
              ratio: contentWidth / contentHeight, naturalRatio: image.naturalWidth / image.naturalHeight,
              breakInside: style.breakInside,
            };
          });
        });
        assert.ok(diagrams.length, `${file}: selected document must contain diagrams`);
        assert.equal(await page.$$eval(".diagram-details, img.diagram-detail", (nodes) => nodes.length), 0);
        for (const image of diagrams) {
          assert.ok(image.nativeWidth > 0 && image.nativeWidth <= 480, `${file}: native diagram width`);
          assert.ok(image.nativeHeight > 0 && image.nativeHeight <= 650, `${file}: native diagram height`);
          assert.ok(image.width <= 480 && image.height <= 650, `${file}: diagram must not be upscaled`);
          assert.ok(Math.abs(image.ratio / image.naturalRatio - 1) < 0.02, `${file}: preserve complete image ratio`);
          assert.equal(image.breakInside, "avoid", `${file}: keep image together`);
        }
        diagramMeasurements.push({ file, viewport: width, diagrams });
      }
    }
    const build = JSON.parse(await fs.readFile(path.join(path.dirname(epub), "build.json"), "utf8"));
    assert.equal(diagramMeasurements.filter((item) => item.viewport === 375)
      .reduce((sum, item) => sum + item.diagrams.length, 0), 2 * build.occurrences.mermaid,
    "inspect every diagram occurrence in both chapter text and its complete-image page");
    await fs.writeFile(path.join(path.dirname(epub), "layout.json"), JSON.stringify({
      epub_sha256: createHash("sha256").update(await fs.readFile(epub)).digest("hex"),
      language, mode: fixture ? "fixture" : "full-book",
      selected_chapters: chapters, formula_return: { ...formulaChapter, occurrence: target.occurrence },
      viewport_width: 375, passed: true, measurements, diagramMeasurements,
    }, null, 2));
  } finally {
    if (browser) await browser.close();
    if (server?.listening) await new Promise((resolve) => server.close(resolve));
    await fs.rm(extracted, { recursive: true, force: true });
  }
});
