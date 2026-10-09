#!/usr/bin/env python3
"""Centralize explicit chapter citations without inferring new source attribution."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit, urlunsplit

from build_book import segments, visible_headings, language_path
from markdown_links import markup_url, rewrite_inline_links, rewrite_links


REGISTRY = "book/bibliography.json"
HEADINGS = {
    "en": {"References", "References and source boundaries", "1.14 References",
           "2.8 Sources and Further Reading"},
    "zh-CN": {"参考资料", "参考资料与来源边界", "1.14 参考资料", "2.8 来源与继续阅读"},
}
MIGRATED = "<!-- centralized-bibliography -->"


def external(raw):
    url = markup_url(raw)[0]
    return url if urlsplit(url).scheme in ("https", "http") else None


def source_section(text, path, language):
    """Recognize only the known final H2 source section, outside protected text."""
    headings = visible_headings(list(segments(text, path, preserve_comments=True)))
    matches = [m for m in headings if m[1] == "##" and m[2] in HEADINGS[language]]
    if len(matches) != 1:
        raise ValueError(f"{path}: expected one explicit trailing source section, found {len(matches)}")
    heading = matches[0]
    if any(m.start() > heading.start() and len(m[1]) <= 2 for m in headings):
        raise ValueError(f"{path}: source section is not trailing; review its boundaries")
    start = text.find("\n", heading.end())
    start = len(text) if start == -1 else start + 1
    tail = "".join(re.sub(r"[^\n]", " ", content) if protected else content
                   for protected, content in segments(text[start:], path, preserve_comments=True))
    # Navigation and rights notices stay in their source chapter.
    footer = re.search(
        r"^(?:Back to (?:the )?\[|返回\s*\[|(?:本文原创|原文与图示|原创文档|原创中文|原创文字)).*$",
        tail, re.M,
    )
    end = start + footer.start() if footer else len(text)
    # A separator immediately before a footer belongs to the footer.
    separator = re.search(r"\n---[ \t]*\n\s*$", text[start:end])
    if separator and tail[separator.start() + 1:separator.start() + 4] == "---":
        end = start + separator.start()
    return start, end, text[start:end]


def relocated(text, source, destination):
    def move(raw):
        url = markup_url(raw)[0]
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path:
            if not parsed.path and parsed.fragment:
                target = os.path.relpath(source, str(Path(destination).parent))
                return target + "#" + parsed.fragment
            return raw
        target = os.path.normpath(str(Path(source).parent / unquote(parsed.path)))
        relative = os.path.relpath(target, str(Path(destination).parent))
        return urlunsplit(("", "", relative, parsed.query, parsed.fragment))
    return rewrite_links(text, source, move)


class Bibliography:
    def __init__(self, registry=None):
        self.data = registry or {"schema_version": 1, "entries": [], "chapters": {}}
        if self.data["schema_version"] != 1:
            raise ValueError("Unsupported bibliography schema")
        self.urls = {}
        for number, entry in enumerate(self.data["entries"], 1):
            if entry["number"] != number or entry["url"] in self.urls:
                raise ValueError("Bibliography numbers must be consecutive and URLs unique")
            self.urls[entry["url"]] = entry

    def register(self, text, path, language):
        def collect(raw, label, original):
            url = external(raw)
            if url:
                if url not in self.urls:
                    entry = {"number": len(self.urls) + 1, "url": url, "labels": {}, "links": {}}
                    self.urls[url] = entry
                    self.data["entries"].append(entry)
                entry = self.urls[url]
                entry["labels"].setdefault(language, label)
                entry["links"].setdefault(language, original)
            return original
        rewrite_inline_links(text, path, collect)

    def cite(self, text, path, language, central=False):
        destination = language_path("docs/book/references.md", language)
        relative = "" if central else os.path.relpath(destination, str(Path(path).parent))

        def replace(raw, label, original):
            url = external(raw)
            if not url:
                return original
            number = self.urls[url]["number"]
            return f'{label}<sup>[【{number}】]({relative}#ref-{number})</sup>'
        return rewrite_inline_links(text, path, replace)

    def render(self, language):
        zh = language == "zh-CN"
        lines = [
            "---",
            ("description: 全书统一编号的参考资料、版本与访问说明，以及各章延伸阅读的来源边界。"
             if zh else
             "description: Globally numbered sources, version and access notes, and chapter-specific further-reading boundaries."),
            "---", "",
            "# 参考资料与延伸阅读" if zh else "# References and Further Reading", "",
            ("全书两种语言使用相同的参考编号。正文中的上标【数字】链接到对应来源；编号仅标识资料，"
             "不表示资料的优先级。章节末尾原有的阅读建议和来源限定保留在下方“各章阅读说明”中。"
             "仅列为延伸阅读的资料不被视为某一段论述的直接证据。"
             if zh else
             "Both language editions use the same reference numbers. Superscript 【numbers】 in the text "
             "link to the corresponding source; numbers identify sources, not their importance. "
             "The original chapter-end reading suggestions and source qualifications remain under "
             "“Chapter reading notes” below. A source listed only as further reading is not presented "
             "as direct evidence for an individual paragraph."),
            "", "## 编号来源" if zh else "## Numbered sources", "",
        ]
        for entry in self.data["entries"]:
            number = entry["number"]
            # Proper source titles stay in their original language if no localized title was supplied.
            link = entry["links"].get(language) or entry["links"].get("en") or next(iter(entry["links"].values()))
            lines.extend((f'<a id="ref-{number}"></a>', "", f"**【{number}】** {link}", ""))
        lines.extend(("## 各章阅读说明" if zh else "## Chapter reading notes", ""))
        for chapter_id, chapter in self.data["chapters"].items():
            localized = chapter[language]
            path = localized["path"]
            destination = language_path("docs/book/references.md", language)
            back = os.path.relpath(path, str(Path(destination).parent))
            notes = relocated(localized["notes"], path, destination)
            notes = self.cite(notes, destination, language, central=True)
            # Keep source-note subheadings readable without adding hundreds of TOC entries.
            chunks = list(segments(notes, destination, preserve_comments=True))
            for heading in reversed(visible_headings(chunks)):
                notes = notes[:heading.start()] + "**" + heading[2] + "**" + notes[heading.end():]
            lines.extend((f'<a id="reading-{chapter_id}"></a>', "",
                          f'**[{localized["title"]}]({back})**', "", notes.strip("\r\n"), ""))
        return "\n".join(lines).rstrip() + "\n"


def migrate(root, apply=False, report=None):
    root = Path(root).resolve()
    registry_path = root / REGISTRY
    bibliography = Bibliography(json.loads(registry_path.read_text()) if registry_path.exists() else None)
    inputs, outputs, chapters = {}, {}, []
    for language in ("en", "zh-CN"):
        manifest = json.loads((root / f"book/{language}/manifest.json").read_text())
        for part in manifest["parts"]:
            for chapter in part["chapters"]:
                path = chapter["path"]
                raw = (root / path).read_bytes()
                text = raw.decode("utf-8")
                inputs[path] = raw
                start, end, notes = source_section(text, path, language)
                title = next(m[2] for m in visible_headings(
                    list(segments(text, path, preserve_comments=True))) if m[1] == "#")
                if MIGRATED not in notes:
                    bibliography.data["chapters"].setdefault(chapter["id"], {})[language] = {
                        "path": path, "title": title, "notes": notes.strip("\r\n"),
                    }
                elif language not in bibliography.data["chapters"].get(chapter["id"], {}):
                    raise ValueError(f"{path}: migration marker has no preserved source notes")
                preserved = bibliography.data["chapters"][chapter["id"]][language]["notes"]
                # Prefer bibliographic titles over short narrative labels for newly seen URLs.
                bibliography.register(preserved, path, language)
                bibliography.register(text, path, language)
                chapters.append((chapter["id"], language, path, text, start, end))
    for chapter_id, language, path, text, start, end in chapters:
        target = os.path.relpath(language_path("docs/book/references.md", language), str(Path(path).parent))
        pointer = (f"本章的参考资料、阅读建议与来源说明见[集中参考资料章节]({target}#reading-{chapter_id})。"
                   if language == "zh-CN" else
                   f"See the [central bibliography]({target}#reading-{chapter_id}) for this chapter’s "
                   "sources, reading suggestions, and source notes.")
        suffix = text[end:]
        text = text[:start] + "\n" + MIGRATED + "\n" + pointer + "\n" + ("\n" + suffix if suffix else "")
        outputs[path] = bibliography.cite(text, path, language)
    for language in ("en", "zh-CN"):
        path = language_path("docs/book/references.md", language)
        outputs[path] = bibliography.render(language)
    outputs[REGISTRY] = json.dumps(bibliography.data, ensure_ascii=False, indent=2) + "\n"
    changed = [p for p, text in outputs.items()
               if not (root / p).exists() or (root / p).read_bytes() != text.encode("utf-8")]
    result = {
        "sources": len(bibliography.urls), "changed": changed,
        "reviewed_english_paths": [p for p in inputs if not p.endswith(".zh.md")],
        "source_sha256": {p: hashlib.sha256(raw).hexdigest() for p, raw in inputs.items()},
    }
    if apply:
        for path, raw in inputs.items():
            if (root / path).read_bytes() != raw:
                raise ValueError(f"{path}: changed during migration; rerun against current sources")
        for path in changed:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(outputs[path], encoding="utf-8")
    if report:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="write only after parsing both complete editions")
    mode.add_argument("--check", action="store_true", help="fail if sources or generated bibliography are stale")
    parser.add_argument("--report", type=Path, help="write exact reviewed English paths and source hashes")
    args = parser.parse_args()
    result = migrate(args.root, args.apply, args.report)
    print(f"{result['sources']} numbered sources; {len(result['changed'])} files "
          f"{'updated' if args.apply else 'would change (dry run)'}")
    if args.check and result["changed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
