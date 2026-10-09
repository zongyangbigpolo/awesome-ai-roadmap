#!/usr/bin/env python3
"""Assemble the repository's Markdown subset; never modify chapter sources."""

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = ("en", "zh-CN")
DEFAULT_MANIFEST = "book/en/manifest.json"
INDEX_PATH = "docs/book/README.md"
CHAPTER = re.compile(r"^(\d{2})-.+\.md$")
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", re.M)
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
SPECIAL = re.compile(
    r"(?P<comment><!--)"
    r"|(?P<code>`+)"
    r"|(?P<math>(?<!\\)\$(?!\$))",
)
ATTRIBUTION = re.compile(
    r"(?:本文原创讲解与示意图|原文与图示|原创文档与图示|原创文档与图"
    r"|原创中文说明、案例、示例与图示|原创文字与图示)：Polo Li，"
    r"(?:(?:按|采用) )?(?:\[CC BY 4\.0\]\(https://creativecommons\.org/licenses/by/4\.0/\)"
    r"|CC BY 4\.0)(?: 授权| 许可)?[。；]"
    r"(?:(?:外部案例出处见上方链接|第三方资料与代码遵循各自项目的许可"
    r"|引用资料归原作者所有|引用资料的权利与许可归原作者|引用资料的权利归原作者)。)?"
)
RETURN_LINK = re.compile(
    r"^(?:返回|Back to) \[[^\n]+\]\((?:[^\n]+/)?README(?:\.zh)?\.md\)[。.][ \t]*$", re.M)
REFERENCE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(.*)$", re.M)


class BookError(ValueError):
    """An input cannot be assembled without losing its meaning."""


def require(condition, message):
    if not condition:
        raise BookError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest_for(language):
    require(language in LANGUAGES, f"unsupported language: {language}")
    return f"book/{language}/manifest.json"


def generated_dir(root, language):
    require(language in LANGUAGES, f"unsupported language: {language}")
    return Path(root) / "book" / language / "generated"


def language_path(path, language):
    require(language in LANGUAGES, f"unsupported language: {language}")
    base = str(path).removesuffix(".zh.md")
    if base == str(path):
        base = str(path).removesuffix(".md")
    require(base != str(path), f"expected Markdown path: {path}")
    return base + (".md" if language == "en" else ".zh.md")


def path_language(path):
    return "zh-CN" if str(path).endswith(".zh.md") else "en"


def add_language_arguments(parser):
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--language", choices=LANGUAGES,
                          help="source language (default: en)")
    selector.add_argument("--manifest", help="explicit repository-relative manifest; determines language")


def check_translation_sync(root):
    checker = source_path(Path(root).resolve(), "scripts/check_translations.py")
    result = subprocess.run([sys.executable, str(checker), "--root", str(root)],
                            capture_output=True, text=True)
    require(result.returncode == 0,
            "translation synchronization check failed:\n" + result.stdout + result.stderr)


def chinese(number):
    require(0 < number < 100, f"unsupported Chinese number: {number}")
    digits = "零一二三四五六七八九"
    if number < 10:
        return digits[number]
    tens, units = divmod(number, 10)
    return (digits[tens] if tens > 1 else "") + "十" + (digits[units] if units else "")


def slug(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]*>", "", text).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def block_boundary(body):
    return re.match(r"#{1,6}\s|`{3,}|~{3,}|\$\$$|<!--", body) or thematic_break(body)


def thematic_break(body):
    return re.fullmatch(r"(?:\* *){3,}|(?:- *){3,}|(?:_ *){3,}", body)


class BlockContext:
    """Track list content columns; indentation is relative to its container."""

    def __init__(self):
        self.list_columns = []
        self.paragraph = False

    def classify(self, line):
        expanded = line.expandtabs(4).rstrip("\n")
        body = expanded.lstrip(" ")
        indent = len(expanded) - len(body)
        if not body:
            self.paragraph = False
            return body, 0, False, 0
        marker = None if thematic_break(body) else re.match(r"([-+*]|\d{1,9}[.)])( +|$)", body)
        block = block_boundary(body)
        if marker or block or not self.paragraph:
            while self.list_columns and indent < self.list_columns[-1]:
                self.list_columns.pop()
        base = self.list_columns[-1] if self.list_columns else 0
        relative = max(0, indent - base)
        if marker and relative <= 3:
            padding = len(marker[2])
            # More than four spaces after a marker starts indented code in the item.
            padding = padding if 1 <= padding <= 4 else 1
            base = indent + len(marker[1]) + padding
            self.list_columns.append(base)
            remainder = expanded[base:]
            body = remainder.lstrip(" ")
            relative = len(remainder) - len(body)
            self.paragraph = False
        code = relative >= 4 and not self.paragraph
        self.paragraph = bool(body) and not code and not block_boundary(body)
        return body, base, code, relative


def segments(text, path, preserve_comments=False):
    """Protect code and math; optionally retain comments for lossless source edits."""
    context = BlockContext()
    position = 0
    while position < len(text):
        newline = text.find("\n", position)
        line_end = len(text) if newline == -1 else newline + 1
        if position == 0 or text[position - 1] == "\n":
            body, base, code, relative = context.classify(text[position:line_end])
            if code:
                yield True, text[position:line_end]
                position = line_end
                continue
            fence = re.match(r"(`{3,}|~{3,})", body)
            display = body.rstrip() == "$$"
            if relative <= 3 and (fence or display):
                delimiter = (re.escape(fence[1][0]) + "{" + str(len(fence[1])) + ",}"
                             if fence else r"\$\$")
                closing = re.compile(r"^([ \t]*)" + delimiter + r"[ \t]*(?:\n|$)", re.M)
                stop = next((m for m in closing.finditer(text, line_end)
                             if base <= len(m[1].expandtabs(4)) <= base + 3), None)
                require(stop is not None,
                        f"{path}: unclosed {'code fence' if fence else 'display math'}")
                yield True, text[position:stop.end()]
                position = stop.end()
                context.paragraph = False
                continue
        match = SPECIAL.search(text, position, line_end)
        if match is None:
            yield False, text[position:line_end]
            position = line_end
            continue
        yield False, text[position:match.start()]
        start, end = match.span()
        if match.group("comment"):
            end = text.find("-->", end)
            require(end != -1, f"{path}: unclosed HTML comment")
            if preserve_comments:
                yield True, text[start:end + 3]
            position = end + 3
            continue
        elif match.group("code"):
            stop = re.search(r"(?<!`)" + re.escape(match.group()) + r"(?!`)", text[end:])
            require(stop is not None, f"{path}: unclosed inline code")
            end += stop.end()
        elif match.group("math"):
            stop = re.search(r"(?<!\\)\$(?!\$)", text[end:].split("\n", 1)[0])
            if stop is None:
                yield False, text[start:end]
                position = end
                continue
            end += stop.end()
        yield True, text[start:end]
        position = end


def inside(root, path):
    return path == root or root in path.parents


def visible_headings(chunks):
    text = "".join(content for _, content in chunks)
    mask = "".join(re.sub(r"[^\n]", " ", content) if protected else content
                   for protected, content in chunks)
    return [match for match in HEADING.finditer(text) if mask[match.start()] == "#"]


def protect(chunks):
    """Keep complete link labels visible while hiding code/math from rewriting."""
    replacements, pieces = {}, []
    for protected, content in chunks:
        require("\x00" not in content, "NUL is not valid in Markdown input")
        if protected:
            token = f"\x00{len(replacements)}\x00" + "\n" * content.count("\n")
            replacements[token] = content
            pieces.append(token)
        else:
            pieces.append(content)
    pattern = re.compile("|".join(re.escape(token) for token in replacements)) if replacements else None

    def restore(value):
        return pattern.sub(lambda m: replacements[m[0]], value) if pattern else value

    return "".join(pieces), restore


def reference_key(label):
    return " ".join(label.lower().split())


def source_path(root, value):
    require(isinstance(value, str), "source path must be a string")
    path = PurePosixPath(value)
    require(not path.is_absolute() and "\\" not in value and
            ".." not in path.parts and str(path) == value,
            f"non-canonical source path: {value}")
    result = (root / value).resolve()
    require(inside(root, result), f"source escapes repository: {value}")
    require(result.is_file(), f"missing source: {value}")
    require(result == root / value, f"symlink source is not allowed: {value}")
    return result


def object_keys(value, keys, label):
    require(isinstance(value, dict), f"{label}: expected object")
    require(set(value) == set(keys), f"{label}: expected fields {', '.join(keys)}")


def nonempty(value, label):
    require(isinstance(value, str) and value.strip() and "\n" not in value,
            f"{label}: expected nonempty single-line string")


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


@dataclass
class Document:
    id: str
    path: str
    number: int = 0
    part_number: int = 0
    language: str = "en"
    title: str = ""
    chunks: list = field(default_factory=list)
    headings: dict = field(default_factory=dict)
    aliases: dict = field(default_factory=dict)
    references: dict = field(default_factory=dict)

    @property
    def label(self):
        if self.number:
            if self.language == "en":
                return f"Part {self.part_number}, Chapter {self.number}: {self.title}"
            return f"第{chinese(self.part_number)}篇 第{self.number}章：{self.title}"
        return self.title


class Book:
    def __init__(self, root=ROOT, manifest=None, language=None):
        self.root = Path(root).resolve()
        self.manifest_path = source_path(self.root, manifest or manifest_for(language or "en"))
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"),
                                   object_pairs_hook=no_duplicate_keys)
        require(isinstance(self.manifest, dict), "manifest: expected object")
        self.language = self.manifest.get("language")
        require(self.language in LANGUAGES, f"unsupported language: {self.language}")
        require(language is None or language == self.language,
                f"requested language {language} differs from manifest language {self.language}")
        self.generated_dir = generated_dir(self.root, self.language)
        self.index_path = language_path(INDEX_PATH, self.language)
        self.documents = {}
        self.parts = []
        self.assets = {}
        self.hashes = {}
        self.anchors = {"contents"}
        self.validate_manifest()
        self.validate_pair()
        for document in self.documents.values():
            self.read_document(document)
        require(self.front[0].title == self.manifest["title"],
                "manifest title differs from title-page H1")

    def add_anchor(self, anchor):
        require(anchor not in self.anchors, f"duplicate book anchor: {anchor}")
        self.anchors.add(anchor)
        return anchor

    def entries(self, entries, part_number=0, topic=None):
        require(isinstance(entries, list) and entries, "entries must be a nonempty list")
        result = []
        for number, entry in enumerate(entries, 1):
            object_keys(entry, ("id", "path"), "entry")
            require(isinstance(entry["id"], str) and ID.fullmatch(entry["id"]),
                    f"invalid stable ID: {entry['id']}")
            path = source_path(self.root, entry["path"])
            require(path.suffix == ".md", f"expected Markdown source: {entry['path']}")
            require(path_language(entry["path"]) == self.language,
                    f"{self.language} manifest contains wrong-language path: {entry['path']}")
            require(entry["path"] not in self.documents, f"duplicate source: {entry['path']}")
            self.add_anchor(entry["id"])
            if topic:
                require(PurePosixPath(entry["path"]).parts[:2] == ("docs", topic),
                        f"chapter outside topic {topic}: {entry['path']}")
                filename = CHAPTER.fullmatch(path.name)
                require(filename and int(filename[1]) == number,
                        f"{topic}: chapters must be in original numeric order 1..N: {path.name}")
            else:
                require(PurePosixPath(entry["path"]).parent == PurePosixPath("docs/book"),
                        f"front/back matter must be in docs/book: {entry['path']}")
                require(path.name not in ("README.md", "README.zh.md"), "website index is not book matter")
            document = Document(entry["id"], entry["path"], number if topic else 0, part_number, self.language)
            self.documents[document.path] = document
            result.append(document)
        return result

    def validate_manifest(self):
        data = self.manifest
        object_keys(data, ("schema_version", "language", "edition", "title", "chapter_count",
                           "source_url", "front_matter", "parts", "back_matter"), "manifest")
        require(type(data["schema_version"]) is int and data["schema_version"] == 1,
                "unsupported schema_version")
        require(data["language"] in LANGUAGES, "unsupported manifest language")
        for key in ("edition", "title", "source_url"):
            nonempty(data[key], key)
        source_url = urlsplit(data["source_url"])
        require(source_url.scheme == "https" and source_url.netloc and
                not source_url.query and not source_url.fragment and
                data["source_url"].endswith("/"),
                "source_url must be an HTTPS directory URL")
        require(type(data["chapter_count"]) is int and data["chapter_count"] > 0,
                "chapter_count must be a positive integer")
        self.front = self.entries(data["front_matter"])
        require(self.front[0].id == "title-page", "front matter must start with title-page")
        require(isinstance(data["parts"], list) and data["parts"], "parts must be a nonempty list")
        topics = set()
        for number, part in enumerate(data["parts"], 1):
            object_keys(part, ("id", "title", "chapters"), "part")
            require(isinstance(part["id"], str) and ID.fullmatch(part["id"]), "invalid topic ID")
            require(part["id"] not in topics, f"duplicate topic: {part['id']}")
            topics.add(part["id"])
            nonempty(part["title"], "part title")
            self.add_anchor("part-" + part["id"])
            self.parts.append((part, self.entries(part["chapters"], number, part["id"])))
        self.back = self.entries(data["back_matter"])
        require(self.back[-1].id == "colophon", "back matter must end with colophon")
        discovered = {p.relative_to(self.root).as_posix()
                      for p in (self.root / "docs").rglob("[0-9][0-9]-*.md")
                      if path_language(p) == self.language}
        included = {d.path for d in self.documents.values() if d.number}
        require(discovered == included,
                f"chapter coverage mismatch; missing={sorted(discovered - included)}, "
                f"unexpected={sorted(included - discovered)}")
        require(len(included) == data["chapter_count"],
                f"chapter_count={data['chapter_count']}, actual={len(included)}")

    def validate_pair(self):
        other_language = "zh-CN" if self.language == "en" else "en"
        other_path = source_path(self.root, manifest_for(other_language))
        other = json.loads(other_path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
        object_keys(other, self.manifest.keys(), "paired manifest")
        require(other["language"] == other_language, "paired manifest has incorrect language")
        require(type(other["schema_version"]) is int and other["schema_version"] == 1,
                "unsupported paired schema_version")
        require(other["chapter_count"] == self.manifest["chapter_count"], "paired chapter counts differ")

        def pair_entries(ours, theirs):
            require(isinstance(theirs, list) and len(ours) == len(theirs), "paired entries differ")
            for own, companion in zip(ours, theirs):
                object_keys(companion, ("id", "path"), "paired entry")
                require(own["id"] == companion["id"], "paired chapter IDs/order differ")
                require(companion["path"] == language_path(own["path"], other_language),
                        f"paired source paths differ: {own['path']}")
                source_path(self.root, companion["path"])

        pair_entries(self.manifest["front_matter"], other["front_matter"])
        pair_entries(self.manifest["back_matter"], other["back_matter"])
        require(isinstance(other["parts"], list) and len(self.manifest["parts"]) == len(other["parts"]),
                "paired part counts differ")
        for own, companion in zip(self.manifest["parts"], other["parts"]):
            object_keys(companion, ("id", "title", "chapters"), "paired part")
            require(own["id"] == companion["id"], "paired part IDs/order differ")
            pair_entries(own["chapters"], companion["chapters"])
        expected = {entry["path"] for part in other["parts"] for entry in part["chapters"]}
        discovered = {path.relative_to(self.root).as_posix()
                      for path in (self.root / "docs").rglob("[0-9][0-9]-*.md")
                      if path_language(path) == other_language}
        require(discovered == expected, "paired-language chapter coverage mismatch")

    def read_document(self, document):
        raw = (self.root / document.path).read_bytes()
        self.hashes[document.path] = digest(raw)
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if text.startswith("---\n"):
            end = re.search(r"^---[ \t]*$", text[4:], re.M)
            require(end is not None, f"{document.path}: unclosed YAML front matter")
            text = text[4 + end.end():].lstrip("\n")
        chunks = []
        for protected, content in segments(text, document.path):
            if not protected and document.number:
                content = RETURN_LINK.sub("", ATTRIBUTION.sub("", content))
                require("Polo Li" not in content,
                        f"{document.path}: unrecognized author notice; centralize in colophon")
            chunks.append((protected, content))
        text = "".join(content for _, content in chunks).rstrip()
        text = re.sub(r"\n---[ \t]*$", "", text).rstrip() + "\n"
        # Re-tokenizing after removing comments also restores adjacent prose spans.
        document.chunks = list(segments(text, document.path))
        prose = "".join(re.sub(r"[^\n]", " ", content) if protected else content
                        for protected, content in document.chunks)
        source_headings = visible_headings(document.chunks)
        h1 = [m for m in source_headings if len(m[1]) == 1]
        require(len(h1) == 1, f"{document.path}: expected exactly one H1")
        require(text[:h1[0].start()].strip() == "", f"{document.path}: content precedes H1")
        document.title = h1[0][2]
        if document.number:
            pattern = (r"^Chapter ([1-9]\d*):\s*(.+)$" if self.language == "en" else
                       r"^第([一二三四五六七八九十百零\d]+)章[：:]\s*(.+)$")
            prefix = re.match(pattern, document.title)
            numbers = (str(document.number),) if self.language == "en" else (
                str(document.number), chinese(document.number))
            require(prefix and prefix[1] in numbers,
                    f"{document.path}: H1 chapter number does not match filename")
            document.title = prefix[2]
        occurrences = {}
        extra = 0
        for match in source_headings:
            level, heading = len(match[1]), match[2]
            require(not document.number or level < 6,
                    f"{document.path}: H6 cannot be demoted; revise heading hierarchy")
            source_slug = slug(heading)
            count = occurrences.get(source_slug, 0)
            occurrences[source_slug] = count + 1
            alias = source_slug + (f"-{count}" if count else "")
            if level == 1:
                anchor = document.id
            elif number := re.match(r"(\d+(?:\.\d+)+)\s", heading):
                anchor = self.add_anchor(document.id + "-s" + number[1].replace(".", "-"))
            else:
                extra += 1
                anchor = self.add_anchor(f"{document.id}-extra-{extra:02}")
            document.headings[match.start()] = anchor
            document.aliases[alias] = anchor
            document.aliases[anchor] = anchor
        protected_text, restore = protect(document.chunks)
        for ref in REFERENCE.finditer(protected_text):
            key = reference_key(restore(ref[1]))
            require(not key.startswith("^"), f"{document.path}: footnotes are not supported")
            require(key not in document.references, f"{document.path}: duplicate reference: {key}")
            document.references[key] = f"{document.id}-ref-{digest(key.encode())[:12]}"
        # Bibliography targets are explicit, globally unique IDs, not TOC headings.
        if document.id == "references":
            citation_anchor = re.compile(r'<a id="((?:ref-[1-9]\d*|reading-[a-z0-9-]+))"></a>')
            for match in citation_anchor.finditer(prose):
                self.add_anchor(match[1])
                document.aliases[match[1]] = match[1]
            prose = citation_anchor.sub("", prose)
        require(not re.search(r"<[A-Za-z][^>]*\b(?:id|name)\s*=", prose),
                f"{document.path}: source HTML anchors need explicit conversion")

    def rewrite_url(self, url, document):
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc:
            require(parsed.scheme in ("http", "https", "mailto") or
                    (not parsed.scheme and parsed.netloc),
                    f"{document.path}: unsupported URL scheme: {url}")
            return url
        require(not parsed.query, f"{document.path}: local link has query: {url}")
        require(not parsed.path.startswith("/") and "\\" not in parsed.path,
                f"{document.path}: invalid local link: {url}")
        target = ((self.root / document.path).parent / unquote(parsed.path)).resolve()
        if not parsed.path:
            target = self.root / document.path
        require(inside(self.root, target), f"{document.path}: link escapes repository: {url}")
        require(target.is_file(), f"{document.path}: missing link or asset: {url}")
        relative = target.relative_to(self.root).as_posix()
        if target.suffix == ".md":
            require(path_language(relative) == self.language,
                    f"{document.path}: cross-language source link is not allowed: {url}")
        fragment = unquote(parsed.fragment)
        if relative in self.documents:
            destination = self.documents[relative]
            if not fragment:
                return "#" + destination.id
            require(fragment in destination.aliases,
                    f"{document.path}: missing heading fragment: {url}")
            return "#" + destination.aliases[fragment]
        if relative in tuple(language_path(path, self.language)
                             for path in ("README.md", "docs/README.md", INDEX_PATH)) and not fragment:
            return "#contents"
        for part, _ in self.parts:
            if relative == language_path(f"docs/{part['id']}/README.md", self.language) and not fragment:
                return "#part-" + part["id"]
        if target.suffix == ".md":
            # Module indexes are not chapters. Keep their precise online meaning.
            if fragment:
                aliases = set()
                counts = {}
                text = target.read_text(encoding="utf-8")
                chunks = list(segments(text, relative))
                for heading in visible_headings(chunks):
                    name = slug(heading[2])
                    count = counts.get(name, 0)
                    aliases.add(name + (f"-{count}" if count else ""))
                    counts[name] = count + 1
                require(fragment in aliases, f"{document.path}: missing index fragment: {url}")
            return (self.manifest["source_url"] + quote(relative, safe="/") +
                    ("#" + quote(fragment) if fragment else ""))
        self.assets[relative] = target
        return "assets/" + quote(relative, safe="/") + ("#" + quote(fragment) if fragment else "")

    def rewrite_destinations(self, content, document):
        # Only the destination is replaced; labels and optional titles remain intact.
        pattern = re.compile(r"(?<!\\)\]\([ \t]*|^ {0,3}\[[^\]\n]+\]:[ \t]*", re.M)
        pieces, position = [], 0
        for match in pattern.finditer(content):
            if match.end() < position:
                continue
            start = match.end()
            angle = content[start:start + 1] == "<"
            begin = start + int(angle)
            end, depth = begin, 0
            while end < len(content):
                char = content[end]
                if char == "\\":
                    end += 2
                    continue
                if angle and char == ">":
                    break
                if not angle:
                    if (char.isspace() or char == ")") and depth == 0:
                        break
                    if char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                end += 1
            require(end < len(content) and depth == 0,
                    f"{document.path}: malformed Markdown link near {content[start:start + 80]!r}")
            if angle:
                require(content[end] == ">", f"{document.path}: unclosed link destination")
            tail = content[end + int(angle):]
            title = r"""(?:"[^"\n]*"|'[^'\n]*'|\([^()\n]*\))"""
            if match[0].lstrip().startswith("]("):
                require(re.match(r"[ \t]*(?:" + title + r"[ \t]*)?\)", tail),
                        f"{document.path}: malformed inline link suffix: {tail[:80]!r}")
            else:
                require(re.match(r"[ \t]*(?:" + title + r"[ \t]*)?(?:\n|$)", tail),
                        f"{document.path}: malformed reference definition")
            raw_url = content[begin:end]
            url = re.sub(r"\\([()])", r"\1", raw_url)
            replacement = self.rewrite_url(url, document)
            pieces.extend((content[position:begin], replacement))
            position = end
        pieces.append(content[position:])
        return "".join(pieces)

    def rewrite_prose(self, content, document, restore):
        require(not re.search(r"\[\^[^\]]+\]", content),
                f"{document.path}: footnotes need an explicit book conversion")
        content = self.rewrite_destinations(content, document)

        def reference(match):
            label, explicit = match[1], match[2]
            key = reference_key(restore(explicit or label))
            if explicit is not None:
                require(key in document.references,
                        f"{document.path}: undefined link reference: {key}")
            if key in document.references:
                return f"[{label}][{document.references[key]}]"
            return match[0]

        lines = []
        for line in content.splitlines(keepends=True):
            definition = REFERENCE.match(line)
            if definition:
                key = reference_key(restore(definition[1]))
                line = line.replace("[" + definition[1] + "]:",
                                    "[" + document.references[key] + "]:", 1)
            else:
                line = re.sub(r"(?<!\\)\[([^\[\]\n]+)\](?:\[([^\]\n]*)\])?(?![(:])",
                              reference, line)
            lines.append(line)
        content = "".join(lines)

        def html_tag(match):
            tag = match[0]
            generated = re.fullmatch(r'<a id="([a-z0-9-]+)">', tag)
            if generated and generated[1] in self.anchors:
                return tag
            require(not re.search(r"\b(?:id|name|srcset)\s*=", tag, re.I),
                    f"{document.path}: source HTML anchors/srcset need explicit conversion")
            attributes = re.compile(r"""\b(href|src)\s*=\s*(["'])(.*?)\2""", re.I)
            require(len(attributes.findall(tag)) == len(re.findall(r"\b(?:href|src)\s*=", tag, re.I)),
                    f"{document.path}: HTML URLs must be quoted")
            return attributes.sub(lambda m: m[1] + "=" + m[2] +
                                  self.rewrite_url(m[3], document) + m[2], tag)

        return re.sub(r"<[A-Za-z][^>]*>", html_tag, content)

    def render_document(self, document):
        def heading(match):
            if match.start() not in document.headings:
                return match[0]
            anchor = document.headings[match.start()]
            level = len(match[1]) + int(bool(document.number))
            title = document.label if len(match[1]) == 1 else match[2]
            return f'<a id="{anchor}"></a>\n\n{"#" * level} {title}'

        text = "".join(content for _, content in document.chunks)
        text = HEADING.sub(heading, text)
        protected_text, restore = protect(segments(text, document.path))
        return restore(self.rewrite_prose(protected_text, document, restore)).strip()

    def contents(self, website=False):
        link = (lambda d: os.path.relpath(self.root / d.path, self.root / "docs/book")) \
            if website else (lambda d: "#" + d.id)
        lines = []
        for document in self.front:
            lines.append(f"- [{document.title}]({link(document)})")
        for number, (part, documents) in enumerate(self.parts, 1):
            count = f" ({len(documents)} chapters)" if self.language == "en" else f"（{len(documents)}章）"
            lines.extend(("", f"## {self.part_label(number, part)}{count}", ""))
            for document in documents:
                lines.append(f"- [{document.label}]({link(document)})")
        lines.extend(("", "## Closing matter and license" if self.language == "en" else "## 后记与许可", ""))
        for document in self.back:
            lines.append(f"- [{document.title}]({link(document)})")
        return "\n".join(lines)

    def index(self):
        if self.language == "en":
            introduction = (
                "---\ndescription: Complete English manuscript reading order across nine parts, "
                "from model foundations to production systems and field delivery.\n---\n\n"
                "# English manuscript: reading order\n\n"
                "Start with the [title page](title-page.md), then read the preface, reading guide, "
                "nine parts, and closing matter. **Chapter numbering restarts in each part.** "
                "The list follows chapter numbers within each part, not the website's module order. "
                "These links use the same chapter sources; there is no separate copy of the prose.\n\n"
            )
        else:
            introduction = (
                "---\ndescription: 按九篇、篇内原章号排列的中文简体书稿完整阅读目录，"
                "从模型原理读到生产系统与现场交付。\n---\n\n"
                "# 中文书稿：线性阅读目录\n\n"
                "从[扉页](title-page.zh.md)开始，依次阅读前言、读法、九篇正文和后附页。"
                "**每篇章号重新开始**；下列顺序以篇内原章号为准，不按网站模块目录排序。"
                "这里链接同一份章节正文，不另存一套副本。\n\n"
            )
        return (introduction +
                f"<!-- Generated by scripts/build_book.py --language {self.language} --write-index; "
                "do not edit the list. -->\n\n" + self.contents(website=True) + "\n")

    def part_label(self, number, part):
        if self.language == "en":
            return f"Part {number}: {part['title']}"
        return f"第{chinese(number)}篇：{part['title']}"

    def assemble(self):
        pages = [self.render_document(self.front[0]),
                 '<a id="contents"></a>\n\n# ' +
                 ("Contents" if self.language == "en" else "目录") + "\n\n" + self.contents()]
        pages.extend(self.render_document(d) for d in self.front[1:])
        for number, (part, documents) in enumerate(self.parts, 1):
            pages.append(f'<a id="part-{part["id"]}"></a>\n\n'
                         f'# {self.part_label(number, part)}')
            pages.extend(self.render_document(d) for d in documents)
        pages.extend(self.render_document(d) for d in self.back)
        return "\n\n".join(pages) + "\n"

    def write(self, output, manuscript):
        output = Path(output).resolve()
        default_dir = self.generated_dir
        require(output.suffix == ".md", "output must have .md extension")
        require(not inside(self.root, output) or inside(default_dir, output),
                f"repository output must stay under book/{self.language}/generated; sources are read-only")
        require(output not in self.assets.values(), "output would overwrite an input asset")
        receipt_path = output.with_suffix(".build.json")
        require(receipt_path.resolve() == receipt_path, "build receipt must not be a symlink")
        if receipt_path.exists():
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
            require(isinstance(previous, dict) and previous.get("language") == self.language,
                    "refusing to overwrite another or unknown language's manuscript")
        destinations = []
        for relative, source in self.assets.items():
            destination = output.parent / "assets" / relative
            require(destination.resolve() == destination, "asset output must not be a symlink")
            require(destination != source, "asset output would overwrite source")
            destinations.append((source, destination))
        output.parent.mkdir(parents=True, exist_ok=True)
        for source, destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        output.write_text(manuscript, encoding="utf-8")
        receipt = {
            "edition": self.manifest["edition"],
            "language": self.manifest["language"],
            "manifest_sha256": digest(self.manifest_path.read_bytes()),
            "source_sha256": self.hashes,
            "asset_sha256": {p: digest(source.read_bytes()) for p, source in self.assets.items()},
            "manuscript_sha256": digest(manuscript.encode("utf-8")),
        }
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_language_arguments(parser)
    parser.add_argument("--check", action="store_true", help="validate without generating manuscript")
    indexes = parser.add_mutually_exclusive_group()
    indexes.add_argument("--write-index", action="store_true", help="regenerate docs/book/README.md")
    indexes.add_argument("--check-index", action="store_true", help="fail if reader index is stale")
    parser.add_argument("--output", type=Path, help="Markdown destination; defaults to ignored generated/")
    args = parser.parse_args(argv)
    try:
        require(not args.check or args.output is None, "--check cannot be combined with --output")
        index_maintenance = args.write_index and not args.check and args.output is None
        if not index_maintenance:
            check_translation_sync(ROOT)
        book = Book(root=ROOT, manifest=args.manifest, language=args.language)
        manuscript = book.assemble()
        index = ROOT / book.index_path
        if args.check_index:
            require(index.is_file() and index.read_text(encoding="utf-8") == book.index(),
                    f"reader index is stale; run python3 scripts/build_book.py --language {book.language} --write-index")
        if args.write_index:
            index.parent.mkdir(parents=True, exist_ok=True)
            index.write_text(book.index(), encoding="utf-8")
        if not args.check and (not args.write_index or args.output):
            output = args.output or book.generated_dir / "manuscript.md"
            book.write(output, manuscript)
            print(f"Markdown draft: {output}")
        print(f"language={book.language} chapters={book.manifest['chapter_count']} parts={len(book.parts)} "
              f"assets={len(book.assets)}")
        return 0
    except (BookError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"book: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
