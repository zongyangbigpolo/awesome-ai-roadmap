"""Bibliography anchors remain native Pandoc targets without becoming TOC entries."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import unittest
import uuid
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_epub as epub


def header(identifier):
    return {"t": "Header", "c": [1, [identifier, [], []], [epub.string(identifier)]]}


def span(identifier):
    return {"t": "Span", "c": [[identifier, [], []], []]}


class BibliographyEpubTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(".artifacts") / ("bibliography-epub-test-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        manifest = self.root / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        self.book = SimpleNamespace(
            language="en", manifest={"title": "Citation test", "language": "en"}, manifest_path=manifest,
            anchors={"chapter", "references", "ref-15", "reading-llm-01"},
            front=[], back=[SimpleNamespace(id="references")],
        )
        self.ast = {"blocks": [
            header("chapter"), header("references"),
            {"t": "Para", "c": [span("ref-15")]},
            {"t": "Para", "c": [span("reading-llm-01")]},
        ]}

    def test_preparation_converts_only_real_bibliography_anchors(self):
        protected = '```html\n<a id="ref-99"></a>\n```\n\n`<a id="ref-98"></a>`\n'
        source = ('<a id="references"></a>\n\n# References\n\n'
                  '<a id="ref-15"></a>\n\n**【15】** Source.\n\n'
                  '<a id="reading-llm-01"></a>\n\nReading notes.\n\n' + protected)
        prepared = epub.prepare_markdown(source)
        self.assertIn("# References {#references}", prepared)
        self.assertIn("[]{#ref-15}", prepared)
        self.assertIn("[]{#reading-llm-01}", prepared)
        self.assertIn(protected, prepared)
        self.assertNotIn("## 【15】", prepared)

    def test_ast_accepts_native_citation_spans_without_promoting_them(self):
        jobs, occurrences = epub.prepare_ast(self.ast, self.book, self.root)
        self.assertEqual(jobs, [])
        self.assertEqual(occurrences, {})
        self.assertEqual([node["c"][1][0] for node in epub.walk(self.ast) if node["t"] == "Header"],
                         ["chapter", "references"])
        self.assertEqual({node["c"][0][0] for node in epub.walk(self.ast) if node["t"] == "Span"},
                         {"ref-15", "reading-llm-01"})

    def test_missing_citation_target_remains_a_failure(self):
        broken = copy.deepcopy(self.ast)
        broken["blocks"].pop()
        with self.assertRaises(epub.BookError):
            epub.prepare_ast(broken, self.book, self.root)

    def test_a_span_cannot_substitute_for_a_missing_chapter_heading(self):
        broken = copy.deepcopy(self.ast)
        broken["blocks"][0] = {"t": "Para", "c": [span("chapter")]}
        with self.assertRaises(epub.BookError):
            epub.prepare_ast(broken, self.book, self.root)

    @unittest.skipUnless(epub.PANDOC.is_file(), "requires the existing pinned Pandoc")
    def test_pandoc_split_epub_rewrites_citations_and_omits_reference_toc_entries(self):
        for language in ("en", "zh-CN"):
            with self.subTest(language=language):
                self.book.language = language
                self.book.manifest["language"] = language
                source = ('<a id="chapter"></a>\n\n# Chapter\n\n'
                          'Claim<sup>[【15】](#ref-15)</sup>. '
                          '[Reading notes](#reading-llm-01).\n\n'
                          '<a id="references"></a>\n\n# References\n\n'
                          '<a id="ref-15"></a>\n\n**【15】** [Source](https://example.org).\n\n'
                          '<a id="reading-llm-01"></a>\n\nSource boundaries.\n')
                ast = json.loads(subprocess.check_output(
                    [str(epub.PANDOC), "--from=markdown-smart-implicit_figures", "--to=json"],
                    input=epub.prepare_markdown(source).encode("utf-8")))
                epub.prepare_ast(ast, self.book, self.root)
                target = self.root / (language + ".epub")
                subprocess.run(
                    [str(epub.PANDOC), "--from=json", "--to=epub3", "--split-level=1",
                     "--toc", "--output=" + str(target)],
                    input=json.dumps(ast).encode("utf-8"), check=True, capture_output=True)
                with zipfile.ZipFile(target) as archive:
                    pages = {name: ET.fromstring(archive.read(name)) for name in archive.namelist()
                             if name.endswith(".xhtml")}
                owners = {element.get("id"): name for name, page in pages.items()
                          for element in page.iter() if element.get("id")}
                chapter = pages[owners["chapter"]]
                citation = chapter.find(".//h:sup/h:a", epub.NS)
                self.assertIsNotNone(citation)
                self.assertEqual("".join(citation.itertext()), "【15】")
                self.assertEqual(citation.get("href"),
                                 Path(owners["ref-15"]).name + "#ref-15")
                self.assertEqual(owners["ref-15"], owners["reading-llm-01"])
                navigation = next(page for name, page in pages.items() if name.endswith("/nav.xhtml"))
                nav_targets = [link.get("href", "") for link in navigation.iter() if link.tag.endswith("}a")]
                self.assertFalse(any("#ref-15" in link or "#reading-llm-01" in link for link in nav_targets))


if __name__ == "__main__":
    unittest.main()
