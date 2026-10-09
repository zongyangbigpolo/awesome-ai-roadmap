"""Explicit EPUB-only integration suite; never discovered by the website workflow."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_epub as epub
import test_build_book as fixtures


class EpubIntegration(unittest.TestCase):
    def test_english_pandoc_renderer_package_links_and_failure_preservation(self):
        self.run_language("en")

    def test_chinese_pandoc_renderer_package_links_and_failure_preservation(self):
        self.run_language("zh-CN")

    def run_language(self, language):
        self.assertTrue(epub.PANDOC.is_file(), "install EPUB tools before running this explicit suite")
        fixture = fixtures.BookTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        english = language == "en"
        first = fixtures.builder.language_path(fixture.first, language)
        third = fixtures.builder.language_path(fixture.third, language)
        title = "# Chapter 1: Models" if english else "# 第一章：模型"
        section = "## 1.1 Mechanism" if english else "## 1.1 中文机制"
        diagram = ('```mermaid\nflowchart LR\n A["Retrieve context"] --> B["Generate an answer"]'
                   ' --> C["Verify facts and sources"] --> D["Human review and delivery"] --> E["Review and update"]\n```\n'
                   if english else '```mermaid\nflowchart LR\n A["中文检索"] --> B["生成答案"]'
                   ' --> C["核对事实与来源"] --> D["人工审阅与交付"] --> E["复盘与更新"]\n```\n')
        links = ("[Next chapter](../02-second/02-second.md#21-mechanism) [Contents](../../README.md)"
                 if english else "[跨章中文标题](../02-second/02-second.zh.md#21-机制) "
                 "[目录](../../README.zh.md)")
        table = ("| Configuration | Formula |\n|---|---|\n"
                 "| retrievalAugmentedGenerationConfiguration | $x_i^2$ |\n"
                 if english else "| 配置 | 公式 |\n|---|---|\n| 检索增强生成 | $x_i^2$ |\n")
        wide_table = ("| Concept | Question | Action | Form |\n|---|---|---|---|\n"
                      "| Tool | Which capability? | Yes | Function |\n"
                      if english else "| 概念 | 问题 | 动作 | 形式 |\n|---|---|---|---|\n"
                      "| 工具 | 可以调用什么能力？ | 是 | 函数 |\n")
        fixture.write(first, title + "\n\n" + section + "\n\n" + links + "\n\n"
                      '`$not_math$` and `` `$$` ``.\n\n'
                      "    $indented_code$\n\n"
                      '````markdown\n```mermaid\nnot a real diagram\n```\n$x$\n````\n\n'
                      + table + "\n" + wide_table + "\n$$\n\\frac{1}{2}\n$$\n\n" + diagram)
        agent_heading = "# Chapter 1: Agents\n\n## 1.1 Mechanism\n\n" if english else "# 第一章：智能体\n\n## 1.1 机制\n\n"
        fixture.write(third, agent_heading + diagram)
        original = {path: path.read_bytes() for path in fixture.root.rglob("*.md")}
        output = fixture.root / "book" / language / "generated/epub"
        real_run = epub.run

        def run(command, **kwargs):
            if list(command) == ["git", "rev-parse", "HEAD"]:
                return "integration-fixture\n"
            return real_run(command, **kwargs)

        def build():
            with patch.object(epub, "Book", lambda **options: fixtures.builder.Book(
                    fixture.root, manifest=options.get("manifest"), language=options.get("language"))), \
                    patch.object(epub, "ROOT", fixture.root), patch.object(epub, "run", run), \
                    patch.object(epub, "check_translation_sync") as sync:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
                    result = epub.main(["--language", language, "--output", str(output)])
                sync.assert_called_once_with(fixture.root)
                return result, errors.getvalue()

        result, errors = build()
        self.assertEqual(result, 0, errors)
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        report = json.loads((output / "build.json").read_text(encoding="utf-8"))
        self.assertEqual(report["language"], language)
        self.assertEqual(report["occurrences"], {"inline": 1, "display": 1, "mermaid": 2})
        self.assertEqual(report["unique_rendered"]["mermaid"], 1)
        self.assertEqual(report["nonlinear_figure_documents"], 2)
        self.assertEqual(report["nonlinear_formula_documents"], 2)
        self.assertNotIn("diagram-detail", report["image_occurrences"])
        self.assertGreater(report["supplemental_image_occurrences"]["diagram-detail"], 0)
        filename = output / f"ai-engineering-interview-{language}.epub"
        previous = filename.read_bytes()
        with zipfile.ZipFile(filename) as archive:
            trees = {name: ET.fromstring(archive.read(name)) for name in archive.namelist()
                     if name.endswith(".xhtml")}
        origin = {}
        for name, tree in trees.items():
            self.assertEqual(tree.get("lang"), language)
            self.assertEqual(tree.get("{http://www.w3.org/XML/1998/namespace}lang"), language)
            for node in tree.iter():
                if node.get("id", "").startswith(("figure-", "formula-")):
                    origin[node.get("id")] = name
            if "/text/" in name:
                self.assertFalse(tree.findall(".//h:img[@class='diagram-detail']", epub.NS))
        return_targets = []
        for name, tree in trees.items():
            if "/figures/" in name:
                link = tree.find(".//h:a", epub.NS)
                self.assertIn("Return" if english else "返回", link.text)
                target, fragment = epub.package_target(name, link.get("href"))
                self.assertEqual(origin[fragment], target)
                if "/figure-" in name:
                    return_targets.append(target)
        self.assertEqual(len(set(return_targets)), 2, "shared PNG must return to the right chapter")
        code = "\n".join(node.text or "" for tree in trees.values()
                         for node in tree.findall(".//h:code", epub.NS))
        self.assertIn("$not_math$", code)
        self.assertIn("$indented_code$", code)
        self.assertIn("not a real diagram", code)
        real_run(["npm", "run", "test:layout", "--prefix", epub.EPUB_DIR],
                 env={**os.environ, "EPUB_LANGUAGE": language, "EPUB_FILE": str(filename)})
        layout = json.loads((output / "layout.json").read_text(encoding="utf-8"))
        self.assertTrue(layout["passed"])
        self.assertEqual(layout["language"], language)
        self.assertEqual(layout["epub_sha256"], report["sha256"])
        fixture.write(first, title + "\n\n$\\notARealCommand{x}$\n")
        result, errors = build()
        self.assertEqual(result, 1)
        self.assertIn("Undefined control sequence", errors)
        self.assertEqual(filename.read_bytes(), previous, "a failed rebuild must preserve last valid EPUB")
        fixture.write(first, title + "\n\n![Remote image](https://example.org/image.png)\n")
        result, errors = build()
        self.assertEqual(result, 1)
        self.assertIn("cannot embed remote", errors)
        self.assertEqual(filename.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
