"""Lightweight EPUB regressions: no Pandoc, Java, Node or browser prerequisite."""

import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_epub as epub


def header(level, identifier, title):
    return {"t": "Header", "c": [level, [identifier, [], []], [epub.string(title)]]}


class EpubTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_wide_table_labels_preserve_cell_markup_and_links(self):
        tree = ET.fromstring(f'''<html xmlns="{epub.XHTML}"><body>
          <table class="original"><thead><tr>
          <th>Concept</th><th>Question <em>answered</em></th><th>执行动作</th><th>Form</th>
          </tr></thead><tbody><tr><td>Tool</td><td><p id="question">Which <code>capability</code>?</p></td>
          <td>Yes</td><td><a href="#question">Function</a> or API</td></tr></tbody></table>
          <table><thead><tr><th>A</th><th>B</th></tr></thead>
          <tbody><tr><td>1</td><td>2</td></tr></tbody></table>
          </body></html>''')
        narrow = tree.findall(".//h:table", epub.NS)[1]
        original_narrow = ET.tostring(narrow)
        epub.label_wide_tables(tree)
        table = tree.find(".//h:table", epub.NS)
        self.assertEqual(table.get("class"), "original wide-table")
        labels = table.findall(".//h:span[@class='cell-label']", epub.NS)
        self.assertEqual([node.text for node in labels],
                         ["Concept", "Question answered", "执行动作", "Form"])
        values = table.findall(".//h:div[@class='cell-value']", epub.NS)
        self.assertEqual(["".join(node.itertext()) for node in values],
                         ["Tool", "Which capability?", "Yes", "Function or API"])
        self.assertEqual(values[1].find("h:p", epub.NS).get("id"), "question")
        self.assertEqual(values[3].find("h:a", epub.NS).get("href"), "#question")
        self.assertEqual(ET.tostring(narrow), original_narrow)

    def test_wide_tables_reject_ambiguous_labels_and_spans(self):
        for first in ['<th colspan="2">A</th>', '<th><img alt="A" src="a.png"/></th>']:
            with self.subTest(first=first):
                tree = ET.fromstring(f'''<html xmlns="{epub.XHTML}"><table><thead><tr>
                  {first}<th>B</th><th>C</th><th>D</th></tr></thead>
                  <tbody><tr><td>1</td><td>2</td><td>3</td><td>4</td></tr></tbody>
                  </table></html>''')
                with self.assertRaises(epub.BookError):
                    epub.label_wide_tables(tree)

    def test_wide_table_blank_corner_preserves_row_names_without_inventing_a_label(self):
        tree = ET.fromstring(f'''<html xmlns="{epub.XHTML}"><table><thead><tr>
          <th/><th>B</th><th>C</th><th>D</th></tr></thead>
          <tbody><tr><td><strong>Tool</strong></td><td>2</td><td>3</td><td>4</td></tr></tbody>
          </table></html>''')
        invalid = ET.fromstring(ET.tostring(tree))
        invalid.find(".//h:thead/h:tr", epub.NS)[1].text = None
        with self.assertRaisesRegex(epub.BookError, "labels after the row-heading"):
            epub.label_wide_tables(invalid)
        epub.label_wide_tables(tree)
        first = tree.find(".//h:tbody/h:tr/h:td", epub.NS)
        self.assertIsNone(first.find("h:span", epub.NS))
        self.assertEqual("".join(first.itertext()), "Tool")
        self.assertEqual(len(tree.findall(".//h:span[@class='cell-label']", epub.NS)), 3)

    def test_language_cli_defaults_and_exclusive_manifest(self):
        with patch.object(epub, "build") as build:
            self.assertEqual(epub.main([]), 0)
            self.assertIsNone(build.call_args.args[0].language)
            self.assertIsNone(build.call_args.args[0].manifest)
            self.assertIsNone(build.call_args.args[0].output)
            self.assertEqual(epub.main(["--language", "en"]), 0)
            self.assertEqual(build.call_args.args[0].language, "en")
            self.assertEqual(epub.main(["--language", "zh-CN"]), 0)
            self.assertEqual(build.call_args.args[0].language, "zh-CN")
            self.assertEqual(epub.main(["--manifest", "custom.json"]), 0)
            self.assertEqual(str(build.call_args.args[0].manifest), "custom.json")
            self.assertIsNone(build.call_args.args[0].language)
        for options in (["--language", "en", "--manifest", "custom.json"],
                        ["--language", "fr"]):
            with self.subTest(options=options), patch("sys.stderr", new=io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    epub.main(options)
                self.assertEqual(error.exception.code, 2)
        self.assertEqual(epub.DEFAULT_OUTPUT, epub.ROOT / "book/en/generated/epub")
        self.assertEqual(epub.BOOK_NAME, "ai-engineering-interview-en")

    def test_failed_translation_check_prevents_compilation(self):
        with patch.object(epub, "check_translation_sync",
                          side_effect=epub.BookError("translation mismatch")) as check, \
                patch.object(epub, "Book") as constructor, patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(epub.main(["--language", "en"]), 1)
        check.assert_called_once_with(epub.ROOT)
        constructor.assert_not_called()

    def test_direct_build_checks_translation_sync_before_reading_book(self):
        with patch.object(epub, "check_translation_sync",
                          side_effect=epub.BookError("missing checker")) as check, \
                patch.object(epub, "Book") as constructor:
            with self.assertRaisesRegex(epub.BookError, "missing checker"):
                epub.build(SimpleNamespace(manifest=None, language="en", output=None))
        check.assert_called_once_with(epub.ROOT)
        constructor.assert_not_called()

    def test_anchors_and_code_math_boundaries(self):
        protected = (
            '````markdown\n<a id="fake"></a>\n\n# 假标题\n```mermaid\nA-->B\n```\n````\n\n'
            '`$code$` `` `$$` ``\n\n    $indented$\n\n'
        )
        source = '<a id="real"></a>\n\n## 中文 `KV` 标题\n\n' + protected + "$x$\n\n$$\ny\n$$\n"
        result = epub.prepare_markdown(source)
        self.assertIn("## 中文 `KV` 标题 {#real}", result)
        self.assertIn(protected, result)
        self.assertEqual(epub.source_counts(source), {"inline": 1, "display": 1})

    def test_actual_mermaid_not_nested_example(self):
        source = "```mermaid\nA-->B\n```\n\n````markdown\n```mermaid\nC-->D\n```\n````\n"
        self.assertEqual(epub.source_counts(source), {"mermaid": 1})

    def test_ast_preserves_examples_removes_manual_contents_and_matter_split(self):
        manifest = self.root / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        book = SimpleNamespace(
            anchors={"title-page", "contents", "preface", "preface-extra", "part-one", "one-01"},
            front=[SimpleNamespace(id="title-page"), SimpleNamespace(id="preface")], back=[],
            manifest={"title": "测试", "language": "zh-CN"}, manifest_path=manifest,
        )
        code = {"t": "CodeBlock", "c": [["", ["python"], []], 'print("$x$")\n```mermaid\n']}
        ast = {"blocks": [
            header(1, "title-page", "测试"), header(1, "contents", "目录"),
            {"t": "Para", "c": [epub.string("人工目录正文")]},
            header(1, "preface", "前言"), header(2, "preface-extra", "读法"),
            header(1, "part-one", "第一篇"), header(2, "one-01", "第一篇 第1章"),
            code,
            {"t": "Math", "c": [{"t": "InlineMath"}, "x_i"]},
            {"t": "Math", "c": [{"t": "InlineMath"}, "x_i"]},
        ]}
        jobs, count = epub.prepare_ast(ast, book, self.root)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(count, {"inline": 2})
        self.assertNotIn("人工目录正文", json.dumps(ast, ensure_ascii=False))
        self.assertEqual(ast["blocks"][2]["c"][0], 3)
        self.assertIn(code, ast["blocks"])
        rendered = {"results": [{"key": jobs[0]["key"], "kind": "inline", "file": "formula.png",
                                 "width": 40, "height": 20, "tiles": []}]}
        result = epub.apply_images(ast, rendered)
        self.assertIn(code, result["blocks"])
        self.assertEqual(sum(node["t"] == "Image" for node in epub.walk(result)), 2)
        self.assertNotIn("_render", json.dumps(result))
        self.assertIn("width:2.00em", json.dumps(result))

    def test_metadata_formula_and_diagram_labels_follow_the_book_language(self):
        keys = {}
        for language in ("en", "zh-CN"):
            with self.subTest(language=language):
                title = "Fundamentals" if language == "en" else "基础"
                manifest = self.root / f"{language}.json"
                manifest.write_text(json.dumps({"language": language, "title": title}))
                book = SimpleNamespace(
                    language=language, manifest={"language": language, "title": title},
                    manifest_path=manifest, anchors={"title-page", "part-one", "one-01"},
                    front=[SimpleNamespace(id="title-page")], back=[],
                )
                ast = {"blocks": [
                    header(1, "title-page", title), header(1, "part-one", title),
                    header(2, "one-01", title),
                    {"t": "Math", "c": [{"t": "InlineMath"}, "x_i"]},
                    {"t": "Math", "c": [{"t": "DisplayMath"}, "x_i"]},
                    {"t": "CodeBlock", "c": [["", ["mermaid"], []], "flowchart LR\n A --> B"]},
                ]}
                jobs, counts = epub.prepare_ast(ast, book, self.root)
                keys[language] = {job["key"] for job in jobs}
                self.assertTrue(all(job["language"] == language for job in jobs))
                self.assertEqual(counts, {"inline": 1, "display": 1, "mermaid": 1})
                self.assertEqual(ast["meta"]["lang"]["c"], language)
                self.assertEqual(ast["meta"]["title"]["c"], title)
                self.assertEqual(ast["meta"]["toc-title"]["c"], "Contents" if language == "en" else "目录")
                rendered = {"results": [
                    dict(job, file=f'{job["key"]}.png', width=100, height=40,
                         tiles=[{"file": "tile.png", "width": 80, "height": 40}]
                         if job["kind"] == "mermaid" else []) for job in jobs]}
                result = epub.apply_images(ast, rendered)
                links = [node["c"] for node in epub.walk(result) if node["t"] == "Link"]
                images = [node["c"] for node in epub.walk(result) if node["t"] == "Image"]
                self.assertEqual(links[0][2][1], epub.LABELS[language]["formula_view"])
                self.assertEqual(epub.text(images[0][1]),
                                 epub.LABELS[language]["formula_alt"].format(source="x_i"))
                self.assertEqual(epub.text(links[2][1]), epub.LABELS[language]["diagram_view"])
                self.assertIn("detail 1/1" if language == "en" else "局部 1/1", epub.text(images[-1][1]))
                spans = [node["c"][0][0] for node in epub.walk(result) if node["t"] == "Span"]
                self.assertEqual(spans, ["formula-1", "formula-2"])
                if language == "en":
                    self.assertNotRegex(json.dumps(result, ensure_ascii=False), r"[\u4e00-\u9fff]")
        self.assertTrue(keys["en"].isdisjoint(keys["zh-CN"]), "render jobs must not share locale cache keys")

    def test_local_non_ascii_asset_and_missing_remote_fail(self):
        asset = self.root / "图片.png"
        asset.write_bytes(b"png")
        self.assertEqual(epub.local_resource("%E5%9B%BE%E7%89%87.png", self.root), asset)
        for url in ("missing.png", "../outside.png", "https://example.com/image.png", "//example.com/a"):
            with self.subTest(url=url), self.assertRaises(epub.BookError):
                epub.local_resource(url, self.root)

    def test_raw_html_rejects_active_or_remote_resources(self):
        for html in ('<script>alert(1)</script>', '<img src="https://example.com/x.png">',
                     '<div onclick="x()">', '<img srcset="x 2x">', '<svg></svg>'):
            with self.subTest(html=html), self.assertRaises(epub.BookError):
                epub.HTMLResources(self.root).feed(html)
        epub.HTMLResources(self.root).feed('<br/><a href="https://example.com">参考</a>')

    def test_output_must_not_replace_sources_or_unowned_directory(self):
        source = self.root / "docs/source.md"
        source.parent.mkdir()
        source.write_text("正文", encoding="utf-8")
        with self.assertRaisesRegex(epub.BookError, "read-only"):
            epub.output_path(source, self.root)
        owned = self.root / "book/zh-CN/generated/epub"
        owned.mkdir(parents=True)
        with self.assertRaisesRegex(epub.BookError, "not an EPUB"):
            epub.output_path(owned, self.root, "zh-CN")
        (owned / "build.json").write_text(
            '{"builder":"build_epub.py","language":"zh-CN"}', encoding="utf-8")
        self.assertEqual(epub.output_path(owned, self.root, "zh-CN"), owned)
        linked = owned.parent / "linked"
        linked.symlink_to(owned, target_is_directory=True)
        with self.assertRaisesRegex(epub.BookError, "symlinks"):
            epub.output_path(linked, self.root)
        self.assertEqual(source.read_text(encoding="utf-8"), "正文")

    def test_output_is_language_safe_even_outside_the_repository(self):
        for language, other in (("en", "zh-CN"), ("zh-CN", "en")):
            with self.subTest(language=language):
                own = self.root / f"book/{language}/generated/epub"
                self.assertEqual(epub.output_path(own, self.root, language), own)
                with self.assertRaisesRegex(epub.BookError, "read-only"):
                    epub.output_path(self.root / f"book/{other}/generated/new", self.root, language)
                with self.assertRaisesRegex(epub.BookError, "another language"):
                    epub.output_path(self.root / f"book/{other}/generated/new",
                                     self.root / "different-repository", language)
        external = self.root / "export"
        external.mkdir()
        receipt = external / "build.json"
        for previous in ("zh-CN", None):
            receipt.write_text(json.dumps({"builder": "build_epub.py", "language": previous}))
            with self.subTest(previous=previous), self.assertRaisesRegex(epub.BookError, "language"):
                epub.output_path(external, self.root / "repository", "en")
        receipt.write_text('{"builder":"build_epub.py","language":"en"}')
        self.assertEqual(epub.output_path(external, self.root / "repository", "en"), external)
        (external / "ai-engineering-interview-zh-CN.epub").write_bytes(b"previous")
        with self.assertRaisesRegex(epub.BookError, "another language"):
            epub.output_path(external, self.root / "repository", "en")
        with self.assertRaisesRegex(epub.BookError, "unsupported EPUB language"):
            epub.output_path(self.root / "book/fr/generated/epub", self.root, "fr")

    def test_build_selects_edition_directory_and_filename_without_heavy_tools(self):
        tools = self.root / "tools"
        dependency = tools / "node_modules/puppeteer/package.json"
        dependency.parent.mkdir(parents=True)
        dependency.write_text("{}")
        pandoc, checker = tools / "pandoc", tools / "epubcheck.jar"
        pandoc.touch()
        checker.touch()

        def command(arguments, **kwargs):
            if arguments == [pandoc, "--version"]:
                return "pandoc 3.6.4\n"
            if arguments == ["java", "-jar", checker, "--version"]:
                return "EPUBCheck v5.2.1\n"
            if "--to=json" in arguments:
                return json.dumps({"blocks": [header(1, "title-page", "Test")]})
            if arguments[0] == "node":
                Path(arguments[-1]).write_text(json.dumps({"results": [], "version": "fixture"}))
            elif "--output" in arguments:
                Path(arguments[-1]).write_bytes(b"unit-test EPUB placeholder")
            elif "--json" in arguments:
                Path(arguments[-1]).write_text('{"messages":[]}')
            elif arguments[:2] == ["git", "rev-parse"]:
                return "fixture-commit"
            return ""

        for language, options in (("en", []), ("zh-CN", ["--language", "zh-CN"]),
                                  ("zh-CN", ["--manifest", "custom.json"])):
            with self.subTest(language=language, options=options):
                manifest = self.root / f"{language}.json"
                manifest.write_text(json.dumps({"title": "Test", "language": language}))
                book = SimpleNamespace(
                    root=self.root, language=language, manifest_path=manifest,
                    manifest={"title": "Test", "language": language}, hashes={},
                    front=[SimpleNamespace(id="title-page")], back=[], anchors={"title-page"},
                    assemble=lambda: "Test",
                    write=lambda path, content: path.write_text(content),
                )
                with patch.object(epub, "Book", return_value=book) as constructor, \
                        patch.object(epub, "EPUB_DIR", tools), \
                        patch.object(epub, "PANDOC", pandoc), patch.object(epub, "EPUBCHECK", checker), \
                        patch.object(epub, "java_command", return_value="java"), \
                        patch.object(epub, "check_translation_sync"), \
                        patch.object(epub, "run", side_effect=command), \
                        patch.object(epub, "repair_links", return_value=0), \
                        patch.object(epub, "audit_epub", return_value={"language": language}), \
                        patch("sys.stdout", new=io.StringIO()):
                    self.assertEqual(epub.main(options), 0)
                self.assertEqual(constructor.call_args.kwargs, {
                    "manifest": "custom.json" if "--manifest" in options else None,
                    "language": "zh-CN" if "--language" in options else None,
                })
                output = self.root / f"book/{language}/generated/epub"
                self.assertTrue((output / f"ai-engineering-interview-{language}.epub").is_file())
                self.assertEqual(json.loads((output / "build.json").read_text())["language"], language)
        self.assertTrue((self.root / "book/en/generated/epub/ai-engineering-interview-en.epub").is_file())

    def test_failed_publication_restores_previous_build(self):
        target = self.root / "epub"
        target.mkdir()
        (target / "old.epub").write_bytes(b"previous")
        staging = self.root / "stage"
        staging.mkdir()
        original = Path.rename

        def fail_new(path, destination):
            if path == staging:
                raise OSError("disk failure")
            return original(path, destination)

        with patch.object(Path, "rename", fail_new), self.assertRaisesRegex(OSError, "disk failure"):
            epub.publish_directory(staging, target)
        self.assertEqual((target / "old.epub").read_bytes(), b"previous")

    def test_failed_command_is_not_success_shaped(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("missing")):
            with self.assertRaisesRegex(epub.BookError, "missing tool"):
                epub.run(["pandoc"])

    def make_package(self, language="zh-CN"):
        title = "测试" if language == "zh-CN" else "Test book"
        book = SimpleNamespace(
            manifest={"language": language, "title": title, "chapter_count": 2},
            front=[SimpleNamespace(id="title-page")],
            parts=[({"id": "one"}, [SimpleNamespace(id="one-01"), SimpleNamespace(id="one-02")])],
            back=[SimpleNamespace(id="colophon")],
            anchors={"title-page", "contents", "part-one", "one-01", "one-02", "中文节", "colophon"},
        )
        order = epub.reading_order(book)
        entries = {"mimetype": b"application/epub+zip",
                   "META-INF/container.xml": b'<container><rootfiles><rootfile full-path="EPUB/content.opf"/></rootfiles></container>'}
        items, spine = [], []
        for number, identifier in enumerate(order):
            name = f"text/ch{number}.xhtml"
            body = f'<h1 id="{identifier}">{identifier}</h1>'
            if identifier == "one-01":
                body += '<a href="#%E4%B8%AD%E6%96%87%E8%8A%82">跨章非ASCII</a><a href="#contents">目录</a>'
            if identifier == "one-02":
                body += '<h2 id="中文节">中文节</h2>'
            if identifier == "contents":
                body = '<nav epub:type="toc" id="toc"><ol>' + "".join(
                    f'<li><a href="ch{i}.xhtml#{key}">{key}</a></li>'
                    for i, key in enumerate(order) if key != "contents") + '</ol></nav>'
            entries["EPUB/" + name] = (
                f'<html xmlns="{epub.XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" '
                f'lang="{language}" xml:lang="{language}">'
                f'<head><title>{title}</title></head><body>{body}</body></html>').encode()
            items.append(f'<item id="i{number}" href="{name}" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="i{number}"/>')
        entries["EPUB/content.opf"] = (
            f'<package xmlns="{epub.OPF}" xmlns:dc="{epub.DC}" version="3.0">'
            f'<metadata><dc:title>{title}</dc:title><dc:language>{language}</dc:language></metadata>'
            '<manifest>' + "".join(items) + '</manifest><spine>' + "".join(spine)
            + '</spine></package>').encode()
        output = self.root / "fixture.epub"
        self.write_package(output, entries)
        return output, book

    def write_package(self, output, entries):
        with zipfile.ZipFile(output, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)

    def test_cross_file_unicode_fragments_native_toc_and_order(self):
        output, book = self.make_package()
        self.assertEqual(epub.repair_links(output, book=book), 2)
        report = epub.audit_epub(output, book, {})
        self.assertEqual(report["chapters"], 2)
        self.assertEqual(report["spine_documents"], 6)
        with zipfile.ZipFile(output) as archive:
            chapter = archive.read("EPUB/text/ch3.xhtml").decode()
        self.assertIn('href="ch4.xhtml#中文节"', chapter)
        self.assertIn('href="ch1.xhtml#contents"', chapter)

    def test_each_language_has_localized_static_supplements_and_occurrence_returns(self):
        for language in ("en", "zh-CN"):
            with self.subTest(language=language):
                output, book = self.make_package(language)
                entries = epub.read_package(output)
                labels = epub.LABELS[language]
                formula_alt = labels["formula_alt"].format(source="x_i")
                diagrams = [labels["diagram_alt"].format(heading=heading) for heading in
                            (("First", "Second") if language == "en" else ("第一", "第二"))]
                additions = "".join(
                    f'<span id="formula-{number}" class="formula inline-math">'
                    f'<a class="formula-link" href="../media/formula.png">'
                    f'<img class="inline-math" src="../media/formula.png" alt="{formula_alt}"/></a></span>'
                    for number in (1, 2))
                additions += "".join(
                    f'<div id="figure-{number}" class="diagram">'
                    f'<p><img class="diagram" src="../media/diagram.png" alt="{alt}"/></p>'
                    f'<a href="../media/diagram.png">{labels["diagram_view"]}</a>'
                    '<div class="diagram-details"><p>'
                    + labels["diagram_part"].format(label=alt, number=1, total=1)
                    + f'</p><img class="diagram-detail" src="../media/tile.png" alt="{alt}"/></div></div>'
                    for number, alt in enumerate(diagrams, 1))
                entries["EPUB/text/ch3.xhtml"] = entries["EPUB/text/ch3.xhtml"].replace(
                    b"</body>", additions.encode() + b"</body>")
                for name in ("formula", "diagram", "tile"):
                    entries[f"EPUB/media/{name}.png"] = name.encode()
                    entries["EPUB/content.opf"] = entries["EPUB/content.opf"].replace(
                        b"</manifest>",
                        f'<item id="{name}" href="media/{name}.png" media-type="image/png"/></manifest>'.encode())
                self.write_package(output, entries)
                epub.repair_links(output, book=book)
                report = epub.audit_epub(output, book, {"inline": 2, "mermaid": 2})
                self.assertEqual(report["language"], language)
                self.assertEqual(report["nonlinear_formula_documents"], 2)
                self.assertEqual(report["nonlinear_figure_documents"], 2)
                entries = epub.read_package(output)
                self.assertNotIn(b"diagram-details", entries["EPUB/text/ch3.xhtml"])
                for kind in ("formula", "figure"):
                    for number in (1, 2):
                        tree = epub.ET.fromstring(entries[f"EPUB/figures/{kind}-{number}.xhtml"])
                        self.assertEqual(tree.get("lang"), language)
                        self.assertEqual(tree.get(epub.XML_LANG), language)
                        link = tree.find("h:body/h:a", epub.NS)
                        self.assertEqual(link.get("href"), f"../text/ch3.xhtml#{kind}-{number}")
                        self.assertEqual(link.text, labels["formula_back" if kind == "formula" else "diagram_back"])
                        title = tree.find("h:head/h:title", epub.NS).text
                        self.assertEqual(title, labels["formula_title"] if kind == "formula" else diagrams[number - 1])
                        self.assertIsNone(tree.find(".//h:script", epub.NS))

    def test_html_and_xml_language_must_match_metadata(self):
        for attribute in ("lang", "xml:lang"):
            output, book = self.make_package("en")
            epub.repair_links(output, book=book)
            entries = epub.read_package(output)
            entries["EPUB/text/ch3.xhtml"] = entries["EPUB/text/ch3.xhtml"].replace(
                f' {attribute}="en"'.encode(), f' {attribute}="zh-CN"'.encode())
            self.write_package(output, entries)
            with self.subTest(attribute=attribute), self.assertRaisesRegex(epub.BookError, "XHTML language"):
                epub.audit_epub(output, book)

    def test_missing_fragments_and_bad_language_fail(self):
        output, book = self.make_package()
        epub.repair_links(output, book=book)
        entries = epub.read_package(output)
        entries["EPUB/text/ch3.xhtml"] = entries["EPUB/text/ch3.xhtml"].replace(
            "ch4.xhtml#中文节".encode(), b"ch4.xhtml#missing")
        self.write_package(output, entries)
        with self.assertRaisesRegex(epub.BookError, "missing EPUB fragment"):
            epub.audit_epub(output, book)
        output, book = self.make_package()
        epub.repair_links(output, book=book)
        book.manifest["language"] = "en"
        with self.assertRaisesRegex(epub.BookError, "incorrect book language"):
            epub.audit_epub(output, book)

    def test_missing_resource_script_and_formula_coverage_fail(self):
        for injection, expected in (
            ('<img src="missing.png" alt="图片"/>', "missing EPUB link/resource"),
            ('<script>1</script>', "non-static XHTML"),
            ('<img src="https://example.com/a.png" alt="图片"/>', "remote/active resource"),
        ):
            output, book = self.make_package()
            epub.repair_links(output, book=book)
            entries = epub.read_package(output)
            entries["EPUB/text/ch3.xhtml"] = entries["EPUB/text/ch3.xhtml"].replace(
                b"</body>", injection.encode() + b"</body>")
            self.write_package(output, entries)
            with self.subTest(injection=injection), self.assertRaisesRegex(epub.BookError, expected):
                epub.audit_epub(output, book)
        output, book = self.make_package()
        epub.repair_links(output, book=book)
        with self.assertRaisesRegex(epub.BookError, "coverage mismatch"):
            epub.audit_epub(output, book, {"inline": 1})

    def test_bad_mimetype_fails(self):
        output, _ = self.make_package()
        entries = epub.read_package(output)
        entries["mimetype"] = b"text/plain"
        self.write_package(output, entries)
        with self.assertRaisesRegex(epub.BookError, "mimetype"):
            epub.read_package(output)


if __name__ == "__main__":
    unittest.main()
