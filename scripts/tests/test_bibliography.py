"""Lossless citation migration and shared website/book source contracts."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_book import Book, BookError
from markdown_links import rewrite_inline_links
from migrate_bibliography import migrate, relocated, source_section


class BibliographyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".artifacts") / ("bibliography-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.chapter = "docs/llm/01-foundations/01-model"
        for language, suffix in (("en", ".md"), ("zh-CN", ".zh.md")):
            manifest = {
                "schema_version": 1, "language": language, "edition": "test", "title": "Test",
                "chapter_count": 1, "source_url": "https://example.org/book/",
                "front_matter": [{"id": "title-page", "path": "docs/book/title-page" + suffix}],
                "parts": [{"id": "llm", "title": "Models", "chapters": [
                    {"id": "llm-01", "path": self.chapter + suffix}]}],
                "back_matter": [{"id": "references", "path": "docs/book/references" + suffix},
                                {"id": "colophon", "path": "docs/book/colophon" + suffix}],
            }
            self.write(f"book/{language}/manifest.json", json.dumps(manifest))
            self.write("docs/book/title-page" + suffix, "# Test\n")
            self.write("docs/book/colophon" + suffix, "# License\n")
            self.write("docs/llm/01-foundations/README" + suffix, "# Module\n")
            self.write(self.chapter + suffix, self.chapter_text(language))

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def chapter_text(self, language):
        title = "# Chapter 1: Model" if language == "en" else "# 第一章：模型"
        heading = "References" if language == "en" else "参考资料"
        return (title + "\n\n## 1.1 Mechanism\n\n"
                'An [explicit `claim`](https://example.org/paper(v1) "Version one") applies here.\n\n'
                "Another paragraph has no explicit citation.\n\n"
                "<!-- [comment](https://example.org/comment) -->\n\n"
                "```markdown\n## References\n[example](https://example.org/code)\n```\n\n"
                "```http\nPOST https://api.example.org/v1/responses\n```\n\n"
                "Use `https://api.example.org/v1/responses` as the example endpoint.\n\n"
                "`[inline](https://example.org/inline)` and $x$ remain.\n\n"
                "    [indented](https://example.org/indented)\n\n"
                f"## {heading}\n\n"
                '- [Author, Paper (2024)](https://example.org/paper(v1) "Version one") — accessed 2026-09-10.\n'
                "- [Different version](https://example.org/paper(v2))\n\n"
                "This is background reading, not evidence for every paragraph.\n\n"
                "Back to the [module](README" + (".zh" if language == "zh-CN" else "") + ".md).\n")

    def test_inline_replacement_preserves_nonlinks(self):
        original = ('[label `x`](https://example.org/a(b) "title") '
                    '![image](https://example.org/i) <!-- [hidden](https://example.org/h) --> '
                    '`[code](https://example.org/c)`')
        changed = rewrite_inline_links(original, "fixture.md",
                                       lambda url, label, full: label + "<sup>【1】</sup>")
        self.assertEqual(changed, 'label `x`<sup>【1】</sup> '
                         '![image](https://example.org/i) <!-- [hidden](https://example.org/h) --> '
                         '`[code](https://example.org/c)`')

    def test_paired_lossless_migration_and_idempotence(self):
        dry = migrate(self.root)
        self.assertEqual(dry["sources"], 2)
        self.assertFalse((self.root / "book/bibliography.json").exists())
        result = migrate(self.root, apply=True)
        self.assertEqual(result["reviewed_english_paths"], [self.chapter + ".md"])
        self.assertEqual(migrate(self.root)["changed"], [])
        for suffix in (".md", ".zh.md"):
            text = (self.root / (self.chapter + suffix)).read_text()
            self.assertIn("explicit `claim`<sup>[【1】](../../book/references" + suffix + "#ref-1)</sup>", text)
            self.assertIn("Another paragraph has no explicit citation.\n", text)
            self.assertIn("<!-- [comment](https://example.org/comment) -->", text)
            self.assertIn("```markdown\n## References\n[example](https://example.org/code)\n```", text)
            self.assertIn("    [indented](https://example.org/indented)", text)
            self.assertIn("```http\nPOST https://api.example.org/v1/responses\n```", text)
            self.assertIn("`https://api.example.org/v1/responses`", text)
            self.assertIn("Back to the [module]", text)
            language = "zh-CN" if suffix == ".zh.md" else "en"
            self.assertNotIn("https://", source_section(text, self.chapter + suffix, language)[2])
            references = (self.root / ("docs/book/references" + suffix)).read_text()
            self.assertIn("accessed 2026-09-10", references)
            self.assertIn("not evidence for every paragraph", references)
            self.assertIn('<a id="ref-1"></a>', references)
            self.assertNotIn("###", references)
            self.assertIn('https://example.org/paper(v1) "Version one"', references)
        registry = json.loads((self.root / "book/bibliography.json").read_text())
        self.assertEqual(registry["entries"][0]["labels"]["en"], "Author, Paper (2024)")

    def test_new_sources_append_without_renumbering(self):
        migrate(self.root, apply=True)
        path = self.root / (self.chapter + ".md")
        path.write_text(path.read_text().replace("Another paragraph", "[New](https://example.org/new). Another paragraph"))
        migrate(self.root, apply=True)
        registry = json.loads((self.root / "book/bibliography.json").read_text())
        self.assertEqual([(e["number"], e["url"]) for e in registry["entries"]],
                         [(1, "https://example.org/paper(v1)"), (2, "https://example.org/paper(v2)"),
                          (3, "https://example.org/new")])

    def test_chapters_without_footers_have_one_final_newline(self):
        for suffix in (".md", ".zh.md"):
            path = self.root / (self.chapter + suffix)
            path.write_text(path.read_text().split("Back to the [module]", 1)[0])
        migrate(self.root, apply=True)
        for suffix in (".md", ".zh.md"):
            text = (self.root / (self.chapter + suffix)).read_text()
            self.assertTrue(text.endswith("\n"))
            self.assertFalse(text.endswith("\n\n"))
        self.assertEqual(migrate(self.root)["changed"], [])

    def test_ci_freshness_check_rejects_unmigrated_and_stale_sources(self):
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / "migrate_bibliography.py"),
                   "--root", str(self.root), "--check"]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
        migrate(self.root, apply=True)
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        references = self.root / "docs/book/references.md"
        references.write_text(references.read_text() + "\nUnreviewed generated edit.\n")
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)

    def test_only_explicit_final_source_headings_match(self):
        text = "# Chapter 1: Model\n\n## 1.2 References in retrieval\n\nTechnical content.\n"
        with self.assertRaisesRegex(ValueError, "expected one"):
            source_section(text, "fixture.md", "en")
        text += "\n## References\n\nSources.\n\n## 1.3 More technical content\n"
        with self.assertRaisesRegex(ValueError, "not trailing"):
            source_section(text, "fixture.md", "en")

    def test_source_section_preserves_protected_footer_examples(self):
        text = ("# Chapter 1: Model\n\n## References\n\n"
                "```text\nBack to [example](README.md).\n```\n\n"
                "<!-- Back to [hidden](README.md). -->\n\n"
                "Access was unavailable; this source establishes scope only.\n\n"
                "---\n\nBack to [module](README.md).\n")
        start, end, notes = source_section(text, "fixture.md", "en")
        self.assertIn("Back to [example]", notes)
        self.assertIn("<!-- Back to [hidden]", notes)
        self.assertIn("Access was unavailable", notes)
        self.assertNotIn("Back to [module]", notes)
        self.assertEqual(text[start:end], notes)
        self.assertTrue(text[end:].startswith("\n---"))

    def test_relocation_preserves_local_fragment_targets_and_examples(self):
        notes = ("See [mechanism](#11-mechanism) and [topic](../README.md#scope).\n\n"
                 "`[example](../README.md)`\n")
        moved = relocated(notes, self.chapter + ".md", "docs/book/references.md")
        self.assertIn("../llm/01-foundations/01-model.md#11-mechanism", moved)
        self.assertIn("../llm/README.md#scope", moved)
        self.assertIn("`[example](../README.md)`", moved)

    def test_assembler_resolves_citation_and_reading_anchors(self):
        migrate(self.root, apply=True)
        for language in ("en", "zh-CN"):
            book = Book(self.root, language=language)
            text = book.assemble()
            self.assertIn('<sup>[【1】](#ref-1)</sup>', text)
            self.assertIn('<a id="ref-1"></a>', text)
            self.assertIn("#reading-llm-01", text)
            self.assertNotIn("ref-1", book.contents())

    def test_assembler_does_not_allow_arbitrary_source_anchors(self):
        migrate(self.root, apply=True)
        path = self.root / "docs/book/references.md"
        path.write_text(path.read_text() + '\n<a id="arbitrary"></a>\n')
        with self.assertRaisesRegex(BookError, "source HTML anchors"):
            Book(self.root, language="en")


if __name__ == "__main__":
    unittest.main()
