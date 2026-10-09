"""Book compilation tests use tiny repositories, not a second copy of the book."""

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_book as builder


class BookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.first = "docs/llm/01-foundations/01-first.zh.md"
        self.second = "docs/llm/02-second/02-second.zh.md"
        self.third = "docs/agent/01-foundations/01-agent.zh.md"
        self.manifest = {
            "schema_version": 1, "language": "zh-CN", "edition": "draft-test",
            "title": "测试书稿", "chapter_count": 3,
            "source_url": "https://example.org/repository/blob/main/",
            "front_matter": [
                {"id": "title-page", "path": "docs/book/title-page.zh.md"},
                {"id": "preface", "path": "docs/book/preface.zh.md"},
            ],
            "parts": [
                {"id": "llm", "title": "大语言模型", "chapters": [
                    {"id": "llm-01", "path": self.first},
                    {"id": "llm-02", "path": self.second},
                ]},
                {"id": "agent", "title": "智能体", "chapters": [
                    {"id": "agent-01", "path": self.third},
                ]},
            ],
            "back_matter": [
                {"id": "acknowledgments", "path": "docs/book/acknowledgments.zh.md"},
                {"id": "colophon", "path": "docs/book/colophon.zh.md"},
            ],
        }
        self.write("docs/book/title-page.zh.md", "---\ndescription: 扉页\n---\n\n# 测试书稿\n")
        self.write("docs/book/preface.zh.md", "# 前言\n\n[作者说明](colophon.zh.md)\n")
        self.write("docs/book/acknowledgments.zh.md", "# 致谢\n\n谢谢读者。\n<!-- 待作者填真实姓名 -->\n")
        self.write("docs/book/colophon.zh.md", "# 作者与许可\n\nPolo Li，CC BY 4.0。\n")
        self.write(self.first, "# 第一章：模型\n\n## 1.1 机制\n\n正文。\n")
        self.write(self.second, "# 第二章：推理\n\n## 2.1 机制\n\n正文。\n")
        self.write(self.third, "# 第一章：智能体\n\n## 1.1 机制\n\n正文。\n")
        self.write("docs/llm/README.zh.md", "# 语言模型\n\n网站目录，不是正文。\n")
        self.write("docs/llm/01-foundations/README.zh.md", "# 基础\n\n网站模块。\n")
        self.write("docs/README.zh.md", "# 网站目录\n")
        self.save_manifest()
        self.make_english_companion()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def save_manifest(self):
        self.write(builder.manifest_for("zh-CN"), json.dumps(self.manifest, ensure_ascii=False))

    def book(self):
        return builder.Book(self.root, language="zh-CN")

    def cli(self, argv):
        with patch.object(builder, "check_translation_sync"):
            return builder.main(["--language", "zh-CN", *argv])

    def make_english_companion(self):
        manifest = json.loads(json.dumps(self.manifest))
        manifest.update(language="en", edition="en-test", title="Test manuscript")
        titles = {"title-page": "Test manuscript", "preface": "Preface",
                  "acknowledgments": "Acknowledgments", "colophon": "Author and license"}
        for entry in manifest["front_matter"] + manifest["back_matter"]:
            entry["path"] = builder.language_path(entry["path"], "en")
            content = "# " + titles[entry["id"]] + "\n\n"
            content += "Polo Li, CC BY 4.0.\n" if entry["id"] == "colophon" else "Reader information.\n"
            self.write(entry["path"], content)
        for part in manifest["parts"]:
            part["title"] = {"llm": "Language models", "agent": "Agents"}[part["id"]]
            for number, entry in enumerate(part["chapters"], 1):
                entry["path"] = builder.language_path(entry["path"], "en")
                self.write(entry["path"], f"# Chapter {number}: Topic {entry['id']}\n\n"
                           f"## {number}.1 Mechanism\n\nText.\n")
        self.write(builder.manifest_for("en"), json.dumps(manifest, ensure_ascii=False))
        for path, title in (("docs/README.md", "Website contents"),
                            ("docs/llm/README.md", "Language models"),
                            ("docs/llm/01-foundations/README.md", "Foundations")):
            self.write(path, "# " + title + "\n")

    def test_order_numbering_toc_and_no_duplicate_body(self):
        text = self.book().assemble()
        labels = re.findall(r"^## (第.+篇 第\d+章：.+)$", text, re.M)
        self.assertEqual(labels, ["第一篇 第1章：模型", "第一篇 第2章：推理", "第二篇 第1章：智能体"])
        self.assertEqual(text.count("\n正文。"), 3)
        self.assertIn("[第一篇 第2章：推理](#llm-02)", text)
        self.assertLess(text.index("# 测试书稿"), text.index("# 目录"))
        self.assertLess(text.index("# 目录"), text.index("# 前言"))
        self.assertLess(text.index("# 致谢"), text.index("# 作者与许可"))
        self.assertNotIn("description:", text)
        self.assertNotIn("待作者填真实姓名", text)
        self.assertNotIn("网站目录，不是正文", text)
        self.assertEqual(text.count("Polo Li"), 1)
        anchors = re.findall(r'<a id="([^"]+)"></a>', text)
        self.assertEqual(len(anchors), len(set(anchors)))
        links = re.findall(r"\]\(#([^)]+)\)", text)
        self.assertFalse(set(links) - set(anchors))

    def test_cross_chapter_same_chapter_index_and_front_back_links(self):
        self.write(self.first, "# 第一章：模型\n\n## 1.1 机制\n\n"
                   "[本节](#11-机制) [本章](#第一章模型)\n"
                   "[下一章](../02-second/02-second.zh.md#21-机制)\n"
                   "[另一篇](../../agent/01-foundations/01-agent.zh.md)\n"
                   "[全书](../../README.zh.md) [本篇](../README.zh.md)\n"
                   "[模块](README.zh.md) [后附页](../../book/colophon.zh.md)\n")
        text = self.book().assemble()
        for expected in ("[本节](#llm-01-s1-1)", "[本章](#llm-01)",
                         "[下一章](#llm-02-s2-1)", "[另一篇](#agent-01)",
                         "[全书](#contents)", "[本篇](#part-llm)",
                         "[后附页](#colophon)", "[作者说明](#colophon)"):
            self.assertIn(expected, text)
        self.assertIn("https://example.org/repository/blob/main/docs/llm/01-foundations/README.zh.md", text)

    def test_module_fragments_after_comments_use_consistent_offsets(self):
        self.write("docs/llm/01-foundations/README.zh.md",
                   "# 模块目录\n\n<!-- Generated navigation -->\n\n## 基础\n\n"
                   "<!-- 多行\n## 不是标题\n注释 -->\n\n## `KV Cache` 基础\n")
        self.write(self.first, "# 第一章：模型\n\n[基础](README.zh.md#基础)\n"
                   "[缓存](README.zh.md#kv-cache-基础)\n")
        text = self.book().assemble()
        self.assertIn("README.zh.md#%E5%9F%BA%E7%A1%80", text)
        self.assertIn("README.zh.md#kv-cache-%E5%9F%BA%E7%A1%80", text)
        with patch.object(builder, "ROOT", self.root), patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(self.cli(["--check"]), 0)
        self.write(self.first, "# 第一章：模型\n\n[不存在](README.zh.md#不是标题)\n")
        with self.assertRaisesRegex(builder.BookError, "missing index fragment"):
            self.book().assemble()

    def test_inline_code_in_headings_keeps_spacing_and_complete_fragment(self):
        self.write(self.first, "# 第一章：`LLM` 模型\n\n## 1.1 `KV Cache` 与缓存\n\n"
                   "[本节](#11-kv-cache-与缓存)\n")
        text = self.book().assemble()
        self.assertIn("## 第一篇 第1章：`LLM` 模型", text)
        self.assertIn("### 1.1 `KV Cache` 与缓存", text)
        self.assertIn("[本节](#llm-01-s1-1)", text)

    def test_repeated_headings_get_unique_anchors_and_source_aliases(self):
        self.write(self.first, "# 第一章：模型\n\n## 参考资料\n\nA\n\n## 参考资料\n\n"
                   "[第二处](#参考资料-1)\n")
        text = self.book().assemble()
        self.assertIn('[第二处](#llm-01-extra-02)', text)

    def test_fences_inline_code_math_and_comments_are_not_rewritten(self):
        protected = (
            "````markdown\n# 假标题\n```python\n[坏路径](missing.zh.md)\n```\n"
            "<!-- 代码里的注释必须保留 -->\n````\n\n"
            "~~~text\n[另一个](missing.zh.md)\n~~~\n\n"
            "`[内联](missing.zh.md)` 和 `` `[代码](missing.zh.md)` ``。\n\n"
            "$$\nA[x](y) = B\n$$\n\n"
            "公式 $A[x](y)$ 不应变成链接。\n\n"
            "    [缩进代码](missing.zh.md)\n"
        )
        self.write(self.first, "# 第一章：模型\n\n" + protected + "\n<!-- 不应出现\n注释结束 -->\n")
        text = self.book().assemble()
        self.assertIn(protected.strip(), text)
        self.assertNotIn("不应出现", text)

    def test_reference_links_are_namespaced_and_destinations_rewritten(self):
        self.write(self.first, "# 第一章：模型\n\n[第二章][ref] [ref] [ref][]\n\n"
                   '[ref]: ../02-second/02-second.zh.md "标题"\n')
        self.write(self.second, "# 第二章：推理\n\n[ref]\n\n[ref]: https://example.org/other\n")
        text = self.book().assemble()
        definitions = re.findall(r"^\[([^]]+)\]: (.+)$", text, re.M)
        self.assertEqual(len(definitions), 2)
        self.assertNotEqual(definitions[0][0], definitions[1][0])
        self.assertEqual(definitions[0][1], '#llm-02 "标题"')
        self.assertIn(f"[第二章][{definitions[0][0]}]", text)
        self.assertEqual(text.count(f"[ref][{definitions[0][0]}]"), 2)

    def test_reference_labels_can_contain_protected_inline_spans(self):
        self.write(self.first, "# 第一章：模型\n\n"
                   "[`KV Cache`][ref] [关于 `KV` 与 `Cache` 的说明][ref]\n"
                   "[`KV Cache`][] [`KV Cache`] [公式 $x_i$][ref]\n"
                   "[`直接链接`](../02-second/02-second.zh.md)\n\n"
                   "[ref]: ../02-second/02-second.zh.md\n"
                   "[`KV Cache`]: ../02-second/02-second.zh.md#21-机制\n\n"
                   "```markdown\n[`KV Cache`][ref]\n[ref]: missing.zh.md\n```\n")
        book = self.book()
        text = book.assemble()
        references = book.documents[self.first].references
        ref = references["ref"]
        code_ref = references["`kv cache`"]
        self.assertIn(f"[`KV Cache`][{ref}]", text)
        self.assertIn(f"[关于 `KV` 与 `Cache` 的说明][{ref}]", text)
        self.assertIn(f"[公式 $x_i$][{ref}]", text)
        self.assertEqual(text.count(f"[`KV Cache`][{code_ref}]"), 2)
        self.assertIn("[`直接链接`](#llm-02)", text)
        self.assertIn("```markdown\n[`KV Cache`][ref]\n[ref]: missing.zh.md\n```", text)
        self.assertNotIn("\x00", text)
        self.write(self.first, "# 第一章：模型\n\n[`KV Cache`][undefined]\n")
        with self.assertRaisesRegex(builder.BookError, "undefined link reference"):
            self.book().assemble()

    def test_nested_lists_rewrite_links_but_preserve_actual_indented_code(self):
        body = (
            "- 列表\n"
            "    - [本章](#第一章模型)\n"
            "        继续阅读[第二章](../02-second/02-second.zh.md)。\n"
            "        1. [前言](../../book/preface.zh.md)\n\n"
            "           [同章](#第一章模型)\n\n"
            "               [列表内代码](missing.zh.md)\n\n"
            "- 第二项\n\n"
            "  继续阅读[第二章](../02-second/02-second.zh.md)。\n\n"
            "      [另一段列表内代码](missing.zh.md)\n\n"
            "正文恢复。\n\n"
            "    - [顶层缩进代码里的列表](missing.zh.md)\n\n"
            "普通段落\n"
            "    [段落延续](#第一章模型)\n"
        )
        self.write(self.first, "# 第一章：模型\n\n" + body)
        text = self.book().assemble()
        self.assertIn("    - [本章](#llm-01)", text)
        self.assertIn("        继续阅读[第二章](#llm-02)", text)
        self.assertIn("        1. [前言](#preface)", text)
        self.assertIn("           [同章](#llm-01)", text)
        self.assertIn("               [列表内代码](missing.zh.md)", text)
        self.assertIn("      [另一段列表内代码](missing.zh.md)", text)
        self.assertIn("    - [顶层缩进代码里的列表](missing.zh.md)", text)
        self.assertIn("    [段落延续](#llm-01)", text)
        self.write(self.first, "# 第一章：模型\n\n- 列表\n    - [坏锚点](#不存在)\n")
        with self.assertRaisesRegex(builder.BookError, "missing heading fragment"):
            self.book().assemble()

    def test_list_container_indentation_handles_tabs_ordered_items_and_fences(self):
        self.write("docs/assets/image.svg", "<svg/>")
        self.write(self.first, "# 第一章：模型\n\n"
                   "10. 外层有序列表\n"
                   "    - ![图](../../assets/image.svg)\n\n"
                   "      ```markdown\n"
                   "      - [代码中的链接](missing.zh.md)\n"
                   "      ```\n\n"
                   "      [代码后的本章](#第一章模型)\n\n"
                   "- 另一列表\n"
                   "\t- [带制表符缩进](#第一章模型)\n\n"
                   "正文。\n\n"
                   "- - -\n\n"
                   "    [分隔线后的缩进代码](missing.zh.md)\n\n"
                   "-     [同一行开始的缩进代码](missing.zh.md)\n")
        text = self.book().assemble()
        self.assertIn("    - ![图](assets/docs/assets/image.svg)", text)
        self.assertIn("      - [代码中的链接](missing.zh.md)", text)
        self.assertIn("      [代码后的本章](#llm-01)", text)
        self.assertIn("\t- [带制表符缩进](#llm-01)", text)
        self.assertIn("    [分隔线后的缩进代码](missing.zh.md)", text)
        self.assertIn("-     [同一行开始的缩进代码](missing.zh.md)", text)

    def test_assets_titles_encoded_paths_and_html(self):
        self.write("docs/assets/图 (1).svg", "<svg>asset</svg>")
        self.write(self.first, '# 第一章：模型\n\n'
                   '![图](<../../assets/图 (1).svg> "图标题")\n'
                   '[下载](../../assets/%E5%9B%BE%20%281%29.svg)\n'
                   '<img src="../../assets/%E5%9B%BE%20%281%29.svg" alt="图">\n'
                   '<a href="../02-second/02-second.zh.md">下一章</a>\n'
                   '[外链](https://example.org/a_(b)?q=x#z "标题")\n')
        book = self.book()
        text = book.assemble()
        encoded = "assets/docs/assets/%E5%9B%BE%20%281%29.svg"
        self.assertIn(f'![图](<{encoded}> "图标题")', text)
        self.assertIn(f'<img src="{encoded}" alt="图">', text)
        self.assertIn('<a href="#llm-02">下一章</a>', text)
        self.assertIn('[外链](https://example.org/a_(b)?q=x#z "标题")', text)
        output = self.root / "book/zh-CN/generated/manuscript.md"
        book.write(output, text)
        self.assertEqual((output.parent / "assets/docs/assets/图 (1).svg").read_text(), "<svg>asset</svg>")
        receipt = json.loads(output.with_suffix(".build.json").read_text())
        self.assertEqual(receipt["manuscript_sha256"], builder.digest(text.encode()))
        self.assertIn("docs/assets/图 (1).svg", receipt["asset_sha256"])
        before = output.with_suffix(".build.json").read_bytes()
        book.write(output, text)
        self.assertEqual(output.with_suffix(".build.json").read_bytes(), before)

    def test_narrow_footer_removal_keeps_citations_and_access_notes(self):
        self.write(self.first, "# 第一章：模型\n\n## 参考资料\n\n"
                   "- [第三方论文](https://example.org/paper)\n\n"
                   "审校口径：截至 2026-09-08；价格仍需核对。原创文字与图示：Polo Li，CC BY 4.0。\n\n"
                   "返回 [FDE 模块目录](README.zh.md)。\n")
        text = self.book().assemble()
        self.assertIn("价格仍需核对。", text)
        self.assertIn("[第三方论文](https://example.org/paper)", text)
        self.assertNotIn("返回 [FDE", text)
        self.assertEqual(text.count("Polo Li"), 1)

    def test_malformed_manifests(self):
        mutations = (
            lambda m: m.update(schema_version=2),
            lambda m: m.update(schema_version=True),
            lambda m: m.update(language="en"),
            lambda m: m.update(chapter_count=4),
            lambda m: m.update(unexpected=True),
            lambda m: m.update(parts=None),
            lambda m: m["parts"][0].update(chapters=[]),
            lambda m: m["parts"][0]["chapters"].reverse(),
            lambda m: m["parts"][0]["chapters"].pop(),
            lambda m: m["parts"][0]["chapters"].append(m["parts"][0]["chapters"][0]),
            lambda m: m["parts"][0]["chapters"][1].update(id="llm-01"),
            lambda m: m["parts"][0]["chapters"][1].update(path=self.third),
            lambda m: m["parts"][0]["chapters"][0].update(path="../outside.zh.md"),
            lambda m: m["parts"][0]["chapters"][0].update(path="/etc/passwd"),
            lambda m: m["parts"][0]["chapters"][0].update(path="./" + self.first),
            lambda m: m["parts"][0]["chapters"][0].update(path="docs\\bad.zh.md"),
            lambda m: m["parts"][0]["chapters"][0].update(path="docs/missing.zh.md"),
            lambda m: m["parts"][0]["chapters"][0].update(id="contains space"),
            lambda m: m["parts"][0]["chapters"][0].update(id="part-llm"),
            lambda m: m.update(title="wrong book"),
        )
        original = json.dumps(self.manifest)
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.manifest = json.loads(original)
                mutation(self.manifest)
                self.save_manifest()
                with self.assertRaises(builder.BookError):
                    self.book()

    def test_new_unlisted_topic_is_not_silently_omitted(self):
        self.write("docs/unlisted/01-module/01-new.zh.md", "# 第一章：新主题\n")
        with self.assertRaisesRegex(builder.BookError, "coverage mismatch"):
            self.book()

    def test_duplicate_json_keys_are_rejected(self):
        self.write(builder.manifest_for("zh-CN"), '{"schema_version": 1, "schema_version": 2}')
        with self.assertRaisesRegex(builder.BookError, "duplicate JSON key"):
            self.book()

    def test_bad_source_paths_and_local_links(self):
        bodies = (
            "[坏链接](missing.zh.md)", "[坏锚点](#does-not-exist)",
            "[坏跨章](../02-second/02-second.zh.md#does-not-exist)",
            "[越界](../../../../outside.zh.md)", "[根路径](/etc/passwd)",
            "[查询](../README.zh.md?query=x)", "[协议](file:///etc/passwd)",
            "[坏链接](../README.zh.md", "[坏链接](<../README.zh.md)",
            "[坏引用][missing]", "[^footnote]", '<img src=missing.svg>',
            '<img srcset="a.svg 1x, b.svg 2x">', '<a id="source-anchor"></a>',
            "Copyright Polo Li, all rights reserved.",
            "```python\n未闭合", "$$\n未闭合", "`未闭合",
            "<!-- 未闭合", "## 1.1 A\n\n## 1.1 B\n",
        )
        for body in bodies:
            with self.subTest(body=body):
                self.write(self.first, "# 第一章：模型\n\n" + body + "\n")
                with self.assertRaises(builder.BookError):
                    self.book().assemble()
        self.write(self.first, "---\ndescription: 未闭合\n# 第一章：模型\n")
        with self.assertRaisesRegex(builder.BookError, "YAML"):
            self.book()

    def test_source_symlink_and_output_overwrite_are_rejected(self):
        (self.root / self.first).unlink()
        (self.root / self.first).symlink_to(self.root / self.second)
        with self.assertRaisesRegex(builder.BookError, "symlink"):
            self.book()
        (self.root / self.first).unlink()
        self.write(self.first, "# 第一章：模型\n")
        book = self.book()
        text = book.assemble()
        with self.assertRaisesRegex(builder.BookError, "read-only"):
            book.write(self.root / self.first, text)
        output = self.root / "book/zh-CN/generated/manuscript.md"
        output.parent.mkdir(parents=True)
        output.with_suffix(".build.json").symlink_to(self.root / self.first)
        with self.assertRaisesRegex(builder.BookError, "receipt"):
            book.write(output, text)
        self.assertFalse(output.exists())

    def test_cli_check_index_regeneration_and_determinism(self):
        with patch.object(builder, "ROOT", self.root), patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(self.cli(["--check"]), 0)
            self.assertFalse((self.root / "book/zh-CN/generated").exists())
            self.assertEqual(self.cli(["--check", "--check-index"]), 1)
            self.assertEqual(self.cli(["--write-index"]), 0)
            self.assertEqual(self.cli(["--check", "--check-index"]), 0)
            self.assertEqual(self.cli(["--check", "--output", "not-written.zh.md"]), 1)
            index_before = (self.root / builder.language_path(builder.INDEX_PATH, "zh-CN")).read_bytes()
            self.write(self.first, "# 第一章：模型新标题\n")
            self.assertEqual(self.cli(["--check", "--check-index"]), 1)
            self.assertEqual(self.cli(["--write-index"]), 0)
            self.assertNotEqual((self.root / builder.language_path(builder.INDEX_PATH, "zh-CN")).read_bytes(), index_before)
            self.assertEqual(self.cli([]), 0)
            output = self.root / "book/zh-CN/generated/manuscript.md"
            before = output.read_bytes()
            self.assertEqual(self.cli([]), 0)
            self.assertEqual(output.read_bytes(), before)

class BilingualBookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = BookTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.english_first = builder.language_path(self.fixture.first, "en")

    def test_default_english_labels_coverage_and_localized_indexes(self):
        english = builder.Book(self.root)
        chinese = builder.Book(self.root, language="zh-CN")
        self.assertEqual(english.language, "en")
        self.assertEqual(len(english.documents), len(chinese.documents))
        self.assertEqual({d.id for d in english.documents.values()},
                         {d.id for d in chinese.documents.values()})
        self.assertIn("Part 1, Chapter 1: Topic llm-01", english.assemble())
        self.assertIn("# Contents", english.assemble())
        self.assertNotIn("第一篇", english.assemble())
        self.assertIn("# English manuscript", english.index())
        self.assertIn("(title-page.md)", english.index())
        self.assertIn("(title-page.zh.md)", chinese.index())
        self.assertEqual(english.index_path, "docs/book/README.md")
        self.assertEqual(chinese.index_path, "docs/book/README.zh.md")

    def test_english_chapter_and_section_links_keep_shared_ids(self):
        self.fixture.write(self.english_first, "# Chapter 1: Models\n\n## 1.1 Mechanism\n\n"
                           "[This section](#11-mechanism) [Next](../02-second/02-second.md#21-mechanism)\n"
                           "[Contents](../../README.md) [Part](../README.md) [Module](README.md)\n")
        text = builder.Book(self.root).assemble()
        for label in ("[This section](#llm-01-s1-1)", "[Next](#llm-02-s2-1)",
                      "[Contents](#contents)", "[Part](#part-llm)"):
            self.assertIn(label, text)
        self.assertIn("docs/llm/01-foundations/README.md", text)
        self.assertNotIn("README.zh.md", text)

    def test_chinese_cannot_masquerade_as_english_and_inverse(self):
        self.fixture.write(self.english_first, "# 第一章：不是英文译稿\n")
        with self.assertRaisesRegex(builder.BookError, "H1 chapter number"):
            builder.Book(self.root)
        self.fixture.write(self.fixture.first, "# Chapter 1: Wrong-language heading\n")
        with self.assertRaisesRegex(builder.BookError, "H1 chapter number"):
            self.fixture.book()

    def test_missing_pair_and_mismatched_manifest_ids_fail(self):
        (self.root / self.english_first).unlink()
        with self.assertRaisesRegex(builder.BookError, "missing source"):
            self.fixture.book()
        self.fixture.make_english_companion()
        english_path = self.root / builder.manifest_for("en")
        manifest = json.loads(english_path.read_text(encoding="utf-8"))
        manifest["parts"][0]["chapters"][0]["id"] = "different-id"
        english_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(builder.BookError, "IDs/order"):
            self.fixture.book()
        english_path.unlink()
        with self.assertRaisesRegex(builder.BookError, "missing source"):
            self.fixture.book()

    def test_cross_language_local_links_fail_in_both_editions(self):
        self.fixture.write(self.english_first, "# Chapter 1: Models\n\n"
                           "[Wrong edition](../02-second/02-second.zh.md)\n")
        with self.assertRaisesRegex(builder.BookError, "cross-language"):
            builder.Book(self.root).assemble()
        self.fixture.write(self.fixture.first, "# 第一章：模型\n\n"
                           "[另一语言](../02-second/02-second.md)\n")
        with self.assertRaisesRegex(builder.BookError, "cross-language"):
            self.fixture.book().assemble()

    def test_manifest_language_and_selected_language_cannot_disagree(self):
        with self.assertRaisesRegex(builder.BookError, "differs from manifest"):
            builder.Book(self.root, manifest=builder.manifest_for("zh-CN"), language="en")
        with self.assertRaisesRegex(builder.BookError, "unsupported language"):
            builder.Book(self.root, language="fr")
        self.fixture.manifest["parts"][0]["chapters"][0]["path"] = self.english_first
        self.fixture.save_manifest()
        with self.assertRaisesRegex(builder.BookError, "wrong-language path"):
            self.fixture.book()

    def test_cli_default_explicit_languages_and_output_separation(self):
        with patch.object(builder, "ROOT", self.root), patch.object(builder, "check_translation_sync") as sync, \
                patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(builder.main([]), 0)
            english = self.root / "book/en/generated/manuscript.md"
            before = english.read_bytes()
            self.assertIn(b"Part 1, Chapter 1", before)
            self.assertEqual(builder.main(["--language", "zh-CN"]), 0)
            self.assertTrue((self.root / "book/zh-CN/generated/manuscript.md").is_file())
            self.assertEqual(english.read_bytes(), before)
            self.assertEqual(builder.main(["--write-index"]), 0)
            self.assertEqual(builder.main(["--language", "zh-CN", "--write-index"]), 0)
            self.assertEqual(builder.main(["--manifest", builder.manifest_for("zh-CN"), "--check"]), 0)
            self.assertEqual(builder.main(["--output", str(self.root / "book/zh-CN/generated/wrong.md")]), 1)
            self.assertGreater(sync.call_count, 0)
            with self.assertRaises(SystemExit):
                builder.main(["--language", "en", "--manifest", builder.manifest_for("en")])

    def test_sync_checker_missing_or_stale_never_silently_passes(self):
        with self.assertRaisesRegex(builder.BookError, "missing source"):
            builder.check_translation_sync(self.root)
        self.fixture.write("scripts/check_translations.py", "import sys\nsys.exit(1)\n")
        with self.assertRaisesRegex(builder.BookError, "synchronization check failed"):
            builder.check_translation_sync(self.root)
        self.fixture.write("scripts/check_translations.py", "import sys\nassert '--root' in sys.argv\n")
        builder.check_translation_sync(self.root)

    def test_write_index_bootstraps_before_sync_but_publication_stays_gated(self):
        with patch.object(builder, "ROOT", self.root), patch("sys.stdout"), patch("sys.stderr"), \
                patch.object(builder, "check_translation_sync",
                             side_effect=builder.BookError("translation sync is stale")) as sync:
            for language in builder.LANGUAGES:
                self.assertEqual(builder.main(["--language", language, "--write-index"]), 0)
                self.assertTrue((self.root / builder.language_path(builder.INDEX_PATH, language)).is_file())
            sync.assert_not_called()
            for arguments in (["--check"], [], ["--write-index", "--output",
                                               str(self.root / "book/en/generated/manuscript.md")]):
                self.assertEqual(builder.main(arguments), 1)
            self.assertEqual(sync.call_count, 3)
            self.assertFalse((self.root / "book/en/generated/manuscript.md").exists())

    def test_external_output_cannot_replace_the_other_edition(self):
        with tempfile.TemporaryDirectory() as external:
            output = Path(external) / "manuscript.md"
            english = builder.Book(self.root)
            english.write(output, english.assemble())
            previous = output.read_bytes()
            chinese = self.fixture.book()
            with self.assertRaisesRegex(builder.BookError, "another or unknown language"):
                chinese.write(output, chinese.assemble())
            self.assertEqual(output.read_bytes(), previous)


class RepositoryBookTests(unittest.TestCase):
    def test_real_manifest_covers_nine_topics_and_143_chapters(self):
        for language in builder.LANGUAGES:
            with self.subTest(language=language):
                book = builder.Book(language=language)
                self.assertEqual([part["id"] for part, _ in book.parts],
                                 ["llm", "multimodal", "tools", "rag", "agent", "frameworks",
                                  "engineering", "safety", "fde"])
                self.assertEqual([len(documents) for _, documents in book.parts],
                                 [23, 10, 15, 22, 25, 23, 13, 10, 2])
                manuscript = book.assemble()
                pattern = r"^## Part \d+, Chapter \d+:" if language == "en" else r"^## 第.+篇 第\d+章："
                self.assertEqual(len(re.findall(pattern, manuscript, re.M)), 143)
                self.assertEqual(manuscript.count("Polo Li"), 2)
                anchors = re.findall(r'<a id="([^"]+)"></a>', manuscript)
                self.assertEqual(len(anchors), len(set(anchors)))
                self.assertFalse(set(re.findall(r"\]\(#([^)]+)\)", manuscript)) - set(anchors))
                for document in book.documents.values():
                    with self.subTest(path=document.path):
                        rendered = book.render_document(document)
                        expected_attribution = 1 if document.id in {"title-page", "colophon"} else 0
                        self.assertEqual(rendered.count("Polo Li"), expected_attribution)
                        source_code_math = [content for protected, content in document.chunks if protected]
                        assembled_code_math = [content for protected, content in
                                               builder.segments(rendered, document.path)
                                               if protected]
                        self.assertEqual(assembled_code_math, source_code_math)


if __name__ == "__main__":
    unittest.main()
