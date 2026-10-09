#!/usr/bin/env python3
"""Build and validate an offline, reflowable EPUB3 from the existing book manifest."""

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from build_book import (
    Book, BookError, ROOT, add_language_arguments, check_translation_sync, digest,
    generated_dir, inside, protect, require, segments,
)
from install_epub_tools import java_command, InstallError


EPUB_DIR = ROOT / "book/epub"
DEFAULT_OUTPUT = generated_dir(ROOT, "en") / "epub"
PANDOC = EPUB_DIR / ".tools/pandoc/bin/pandoc"
EPUBCHECK = EPUB_DIR / ".tools/epubcheck/epubcheck.jar"
BOOK_NAME = "ai-engineering-interview-en"
XHTML = "http://www.w3.org/1999/xhtml"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
NS = {"h": XHTML, "o": OPF, "dc": DC}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
LABELS = {
    "en": {
        "toc": "Contents",
        "rights": "Original text and diagrams: Polo Li, CC BY 4.0. "
                  "Third-party material retains its own rights; see colophon.",
        "formula_alt": "Formula: {source}",
        "formula_view": "View the complete formula",
        "formula_title": "Complete formula",
        "formula_back": "Return to this formula in the text",
        "diagram_alt": "{heading}: flow or structure diagram",
        "diagram_view": "View this diagram separately",
        "diagram_title": "Complete diagram",
        "diagram_back": "Return to this diagram in the text",
    },
    "zh-CN": {
        "toc": "目录",
        "rights": "原创文字与图示：Polo Li，CC BY 4.0。第三方资料保留各自权利；见版权页。",
        "formula_alt": "公式：{source}",
        "formula_view": "查看完整公式",
        "formula_title": "完整公式",
        "formula_back": "返回正文中的此公式",
        "diagram_alt": "{heading}：流程或结构示意图",
        "diagram_view": "单独查看此图",
        "diagram_title": "完整示意图",
        "diagram_back": "返回正文中的此图",
    },
}


def labels_for(language):
    require(language in LABELS, f"unsupported EPUB language: {language}")
    return LABELS[language]


def book_language(book):
    language = getattr(book, "language", None) or book.manifest["language"]
    labels_for(language)
    require(language == book.manifest["language"], "book and manifest languages differ")
    return language


def run(command, **kwargs):
    try:
        result = subprocess.run([str(value) for value in command], check=True,
                                capture_output=True, text=True, **kwargs)
    except FileNotFoundError as error:
        raise BookError(f"missing tool: {command[0]}; see book/README.md EPUB setup") from error
    except subprocess.CalledProcessError as error:
        raise BookError(f"{command[0]} failed ({error.returncode}):\n"
                        f"{error.stdout}\n{error.stderr}") from error
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.stdout


def output_path(value, root=ROOT, language="en"):
    """A dedicated output directory is replaced only after all checks succeed."""
    raw = Path(value).absolute()
    result = raw.resolve()
    labels_for(language)
    allowed = generated_dir(root, language).resolve()
    require(raw == result, "output path must not contain symlinks or '..'")
    require(not inside(root, result) or inside(allowed, result),
            f"repository output must stay under book/{language}/generated; sources are read-only")
    for other in LABELS.keys() - {language}:
        require(not any(result.parts[index:index + 3] == ("book", other, "generated")
                        for index in range(len(result.parts) - 2)),
                f"output belongs to another language: {other}")
    require(result != allowed, "output must be a dedicated EPUB subdirectory")
    require(not result.exists() or result.is_dir(), "output must be a directory")
    if result.exists():
        receipt = result / "build.json"
        require(receipt.is_file() and not receipt.is_symlink(),
                "existing output is not an EPUB build directory")
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        require(isinstance(previous, dict) and previous.get("builder") == "build_epub.py",
                "refusing to replace a directory not owned by the EPUB builder")
        require(previous.get("language") == language,
                "refusing to replace an EPUB output of another or unknown language")
        require(not any((result / f"ai-engineering-interview-{other}.epub").exists()
                        for other in LABELS.keys() - {language}),
                "output contains an EPUB of another language")
    return result


def prepare_markdown(manuscript):
    # Move assembler-owned anchors onto headings BEFORE Pandoc splits files.
    # Protect code/math so a Markdown example cannot become an actual chapter.
    masked, restore = protect(segments(manuscript, "assembled manuscript"))
    masked = re.sub(r'<a id="(ref-[1-9]\d*|reading-[a-z0-9-]+)"></a>',
                    lambda m: f"[]{{#{m[1]}}}", masked)
    masked = re.sub(r'<a id="([a-z0-9-]+)"></a>\n\n(#{1,6}) ([^\n]+)',
                    lambda m: f"{m[2]} {m[3]} {{#{m[1]}}}", masked)
    return restore(masked)


def source_counts(manuscript):
    result = Counter()
    for protected, content in segments(manuscript, "assembled manuscript"):
        if not protected:
            continue
        if re.match(r"^ {0,3}(?:`{3,}|~{3,})mermaid\s*\n", content):
            result["mermaid"] += 1
        elif re.match(r"^ {0,3}\$\$\s*\n", content):
            result["display"] += 1
        elif content.startswith("$"):
            result["inline"] += 1
    return dict(result)


def walk(value):
    if isinstance(value, dict):
        if "t" in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def text(value):
    return "".join(node.get("c", "") if node["t"] == "Str" else " "
                   for node in walk(value) if node["t"] in ("Str", "Space", "SoftBreak"))


def attr(classes=(), pairs=()):
    return ["", list(classes), [list(pair) for pair in pairs]]


def string(value):
    return {"t": "Str", "c": value}


def metadata(value):
    return {"t": "MetaString", "c": value}


def local_resource(url, directory):
    parsed = urlsplit(url)
    require(not parsed.scheme and not parsed.netloc and not parsed.query,
            f"offline EPUB cannot embed remote/dynamic resource: {url}")
    require(parsed.path and not parsed.path.startswith("/") and "\\" not in parsed.path,
            f"invalid local resource: {url}")
    destination = (directory / unquote(parsed.path)).resolve()
    require(inside(directory.resolve(), destination) and destination.is_file(),
            f"missing or out-of-tree resource: {url}")
    return destination


def static_image(url, directory):
    image = local_resource(url, directory)
    require(image.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif"},
            f"source image must be a static PNG/JPEG/GIF; convert explicitly before export: {url}")
    return image


class HTMLResources(HTMLParser):
    def __init__(self, directory):
        super().__init__()
        self.directory = directory

    def handle_starttag(self, tag, attributes):
        require(tag not in {"script", "iframe", "object", "embed", "style", "link", "svg", "math"},
                f"unsupported raw HTML element: {tag}")
        for key, value in attributes:
            require(not key.startswith("on") and key not in {"srcset", "style"},
                    f"unsupported raw HTML attribute: {key}")
            if key in {"src", "poster", "data"}:
                static_image(value, self.directory)
            if key == "href":
                require(urlsplit(value).scheme in ("", "https", "http", "mailto"),
                        f"unsupported HTML link: {value}")


def prepare_ast(ast, book, directory):
    language = book_language(book)
    labels = labels_for(language)
    blocks, skipping = [], False
    for block in ast["blocks"]:
        if block["t"] == "Header" and block["c"][0] == 1:
            skipping = block["c"][1][0] == "contents"
        if not skipping:
            blocks.append(block)
    ast["blocks"] = blocks
    found = {node["c"][1][0] for node in walk(ast) if node["t"] == "Header"}
    citation_anchors = {anchor for anchor in book.anchors
                        if re.fullmatch(r"ref-[1-9]\d*|reading-[a-z0-9-]+", anchor)}
    spans = {node["c"][0][0] for node in walk(ast) if node["t"] == "Span"}
    require(citation_anchors <= spans, "Pandoc lost stable bibliography anchors")
    require(book.anchors - {"contents"} - citation_anchors <= found,
            "Pandoc lost stable chapter/section anchors")
    ast["meta"] = {
        "title": metadata(book.manifest["title"]),
        "author": {"t": "MetaList", "c": [metadata("Polo Li")]},
        "lang": metadata(language),
        "identifier": metadata("urn:sha256:" + digest(book.manifest_path.read_bytes())),
        "rights": metadata(labels["rights"]),
        "toc-title": metadata(labels["toc"]),
    }
    jobs, occurrences = {}, Counter()
    heading = book.manifest["title"]
    matter = False
    matter_ids = {document.id for document in book.front + book.back}
    for node in walk(ast["blocks"]):
        kind = None
        if node["t"] == "Header":
            if node["c"][0] == 1:
                matter = node["c"][1][0] in matter_ids
            elif matter:
                node["c"][0] = min(6, node["c"][0] + 1)
            heading = text(node["c"][2])
        elif node["t"] == "CodeBlock" and "mermaid" in node["c"][0][1]:
            kind, source = "mermaid", node["c"][1]
        elif node["t"] == "Math":
            kind = "display" if node["c"][0]["t"] == "DisplayMath" else "inline"
            source = node["c"][1]
        elif node["t"] == "Image":
            static_image(node["c"][2][0], directory)
            require(text(node["c"][1]).strip(), "source image needs alternative text")
            occurrences["source_images"] += 1
        elif node["t"] in ("RawBlock", "RawInline"):
            require(node["c"][0] == "html", "unsupported non-HTML raw content")
            HTMLResources(directory).feed(node["c"][1])
        if kind:
            key = digest((language + "\0" + kind + "\0" + source).encode())
            jobs[key] = {"key": key, "kind": kind, "source": source, "language": language}
            # Private fields are removed before the JSON is passed back to Pandoc.
            node["_render"] = key
            node["_heading"] = heading
            occurrences[kind] += 1
    return list(jobs.values()), dict(occurrences)


def apply_images(ast, rendered, language=None):
    language = language or ast.get("meta", {}).get("lang", {}).get("c", "en")
    labels = labels_for(language)
    assets = {item["key"]: item for item in rendered["results"]}
    figure_number = 0
    formula_number = 0
    for item in assets.values():
        if item["kind"] == "mermaid":
            require(0 < item["width"] <= 480 and 0 < item["height"] <= 650,
                    f"diagram {item['key']} is {item['width']}x{item['height']} CSS px; "
                    "simplify the source to at most 480x650, moving details into prose")
            require(not item.get("tiles"), f"diagram {item['key']}: cropped detail tiles are not supported")
            require(not item.get("labelCollisions"),
                    f"diagram {item['key']}: subgraph titles overlap nodes: {item.get('labelCollisions')}")

    def image(item, label, classes, inline=False):
        pairs = [("style", f"width:{item['width'] / 20:.2f}em;")] if inline else []
        if "diagram" in classes:
            pairs = [("style", f"width:{item['width']}px;")]
        return {"t": "Image", "c": [attr(classes, pairs), [string(label)],
                                  ["rendered/" + item["file"], ""]]}

    def transform(value):
        nonlocal figure_number, formula_number
        if isinstance(value, dict):
            key = value.get("_render")
            if key:
                item = assets[key]
                source = value["c"][1]
                if item["kind"] in ("inline", "display"):
                    formula_number += 1
                    inline = item["kind"] == "inline"
                    classes = ["inline-math" if inline else "display-math"]
                    return {"t": "Span", "c": [
                        [f"formula-{formula_number}", ["formula"] + classes, []],
                        [{"t": "Link", "c": [
                            attr(["formula-link"]),
                            [image(item, labels["formula_alt"].format(source=source), classes, inline)],
                            ["rendered/" + item["file"], labels["formula_view"]],
                        ]}],
                    ]}
                label = labels["diagram_alt"].format(heading=value["_heading"])
                figure_number += 1
                blocks = [{"t": "Para", "c": [image(item, label, ["diagram"])]},
                          {"t": "Para", "c": [{"t": "Link", "c": [
                              attr(["figure-link"]), [string(labels["diagram_view"])],
                              ["rendered/" + item["file"], ""],
                          ]}]}]
                return {"t": "Div", "c": [[f"figure-{figure_number}", ["diagram"], []], blocks]}
            return {key: transform(child) for key, child in value.items()}
        if isinstance(value, list):
            return [transform(child) for child in value]
        return value

    return transform(ast)


def package_target(source, url):
    parsed = urlsplit(url)
    require(not parsed.query, f"local EPUB link has query: {url}")
    require(not parsed.path.startswith("/") and "\\" not in parsed.path, f"invalid EPUB URL: {url}")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path))) \
        if parsed.path else source
    require(path != ".." and not path.startswith("../"), f"EPUB URL escapes container: {url}")
    return path, unquote(parsed.fragment)


def read_package(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "duplicate EPUB ZIP members")
        require(names and names[0] == "mimetype" and
                archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED and
                archive.read("mimetype") == b"application/epub+zip", "invalid EPUB mimetype")
        for name in names:
            require(not name.startswith("/") and ".." not in PurePosixPath(name).parts,
                    f"unsafe EPUB member: {name}")
        return {name: archive.read(name) for name in names}


def reading_order(book):
    order = [book.front[0].id, "contents"] + [d.id for d in book.front[1:]]
    for part, documents in book.parts:
        order.extend(["part-" + part["id"]] + [d.id for d in documents])
    return order + [d.id for d in book.back]


def label_wide_tables(tree):
    for table in tree.findall(".//h:table", NS):
        headings = table.findall("h:thead/h:tr", NS)
        if not headings or len(headings[0]) < 4:
            continue
        require(len(headings) == 1, "wide tables require one header row")
        headers = list(headings[0])
        rows = table.findall("h:tbody/h:tr", NS) + table.findall("h:tfoot/h:tr", NS)
        require(all(len(row) == len(headers) for row in rows),
                "wide-table rows must match the header columns")
        cells = headers + [cell for row in rows for cell in row]
        require(all(cell.get("colspan", "1") == "1" and cell.get("rowspan", "1") == "1"
                    for cell in cells), "wide tables with merged cells need explicit layout support")
        require(not any(header.findall(".//h:img", NS) for header in headers),
                "wide-table image headers need explicit text labels")
        labels = [" ".join("".join(header.itertext()).split()) for header in headers]
        require(all(labels[1:]), "wide tables require labels after the row-heading column")
        table.set("class", (table.get("class", "") + " wide-table").strip())
        for row in rows:
            for cell, label in zip(row, labels):
                value = ET.Element(f"{{{XHTML}}}div", {"class": "cell-value"})
                value.text = cell.text
                value.extend(list(cell))
                cell.text = None
                cell[:] = [value]
                if label:
                    heading = ET.Element(f"{{{XHTML}}}span", {"class": "cell-label"})
                    heading.text = label
                    cell.insert(0, heading)


def repair_links(path, resource_hashes=None, book=None):
    """Resolve fragment-only links using actual split XHTML IDs, including raw HTML."""
    entries = read_package(path)
    container = ET.fromstring(entries["META-INF/container.xml"])
    opf_path = container.find(".//{*}rootfile").get("full-path")
    package = ET.fromstring(entries[opf_path])
    language = book_language(book) if book is not None else package.find("o:metadata/dc:language", NS).text
    labels = labels_for(language)
    packaged_assets = {}
    for name, data in entries.items():
        if not name.endswith((".xhtml", ".opf", ".ncx")):
            packaged_assets.setdefault(digest(data), name)
    trees = {name: ET.fromstring(data) for name, data in entries.items() if name.endswith(".xhtml")}
    targets = {}
    for name, tree in trees.items():
        for element in tree.iter():
            identifier = element.get("id")
            if identifier:
                targets.setdefault(identifier, []).append(name)
    nav_files = [name for name, tree in trees.items()
                 if tree.find(".//h:nav[@{http://www.idpf.org/2007/ops}type='toc']", NS) is not None]
    require(len(nav_files) == 1, "expected one native EPUB navigation document")
    nav_body = trees[nav_files[0]].find(".//h:body", NS)
    require(not nav_body.get("id"), "navigation body already has an ID")
    nav_body.set("id", "contents")
    targets["contents"] = [nav_files[0]]
    fixed = 0
    figures = {}
    for name, tree in trees.items():
        label_wide_tables(tree)
        parents = {child: parent for parent in tree.iter() for child in parent}
        for element in tree.iter():
            url = element.get("href", "")
            parsed = urlsplit(url)
            if not url or parsed.scheme or parsed.netloc:
                continue
            target, fragment = package_target(name, url)
            original = unquote(parsed.path)
            if target not in entries and original in (resource_hashes or {}):
                asset = packaged_assets.get(resource_hashes[original])
                require(asset, f"Pandoc did not package linked asset: {url}")
                target = asset
                element.set("href", posixpath.relpath(asset, posixpath.dirname(name)) +
                            ("#" + fragment if fragment else ""))
                fixed += 1
            if target.endswith(".png") and target in entries:
                # EPUB hyperlinks must target content documents, not bare PNGs.
                container = parents.get(element)
                while container is not None and not (
                        {"diagram", "formula"} & set(container.get("class", "").split())):
                    container = parents.get(container)
                require(container is not None and container.get("id"),
                        "linked image must belong to an identified diagram or formula")
                origin_id = container.get("id")
                is_formula = "formula" in container.get("class", "").split()
                figure = "EPUB/figures/" + origin_id + ".xhtml"
                if figure not in figures:
                    images = container.findall(".//h:img", NS)
                    alt = next((image.get("alt") for image in images
                                if package_target(name, image.get("src"))[0] == target), labels["diagram_title"])
                    visible_title = labels["formula_title"] if is_formula else alt
                    figure_tree = ET.Element(f"{{{XHTML}}}html", {
                        "lang": language, XML_LANG: language})
                    head = ET.SubElement(figure_tree, f"{{{XHTML}}}head")
                    ET.SubElement(head, f"{{{XHTML}}}title").text = visible_title
                    for link in tree.findall("h:head/h:link", NS):
                        if link.get("rel") == "stylesheet":
                            stylesheet, _ = package_target(name, link.get("href"))
                            ET.SubElement(head, f"{{{XHTML}}}link", {
                                "rel": "stylesheet", "type": "text/css",
                                "href": posixpath.relpath(stylesheet, "EPUB/figures"),
                            })
                    body = ET.SubElement(figure_tree, f"{{{XHTML}}}body")
                    ET.SubElement(body, f"{{{XHTML}}}a", {
                        "href": posixpath.relpath(name, "EPUB/figures") + "#" + origin_id,
                    }).text = labels["formula_back" if is_formula else "diagram_back"]
                    ET.SubElement(body, f"{{{XHTML}}}p").text = visible_title
                    full_image = ET.SubElement(body, f"{{{XHTML}}}img", {
                        "src": posixpath.relpath(target, "EPUB/figures"), "alt": alt,
                        "class": "full-formula" if is_formula else "diagram",
                    })
                    if not is_formula:
                        original = next(image for image in images
                                        if package_target(name, image.get("src"))[0] == target)
                        if original.get("style"):
                            full_image.set("style", original.get("style"))
                    figures[figure] = figure_tree
                element.set("href", posixpath.relpath(figure, posixpath.dirname(name)))
                fixed += 1
            if not fragment:
                continue
            actual = targets.get(fragment, [])
            if target in actual:
                continue
            require(len(actual) == 1, f"ambiguous or missing internal fragment: {name}: {url}")
            element.set("href", posixpath.relpath(actual[0], posixpath.dirname(name)) + "#" + fragment)
            fixed += 1
        # Avoid ns0 prefixes in XHTML; HTML readers also accept the default namespace.
        ET.register_namespace("", XHTML)
        ET.register_namespace("epub", "http://www.idpf.org/2007/ops")
        entries[name] = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    for name, tree in figures.items():
        entries[name] = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    if book is not None:
        manifest = {package_target(opf_path, item.get("href"))[0]: item.get("id")
                    for item in package.findall("o:manifest/o:item", NS)}
        spine = package.find("o:spine", NS)
        references = {item.get("idref"): item for item in spine}
        desired = []
        for identifier in reading_order(book):
            require(len(targets.get(identifier, [])) == 1, f"missing/duplicate stable ID: {identifier}")
            desired.append(manifest[targets[identifier][0]])
        require(len(desired) == len(set(desired)) and set(desired) == set(references),
                "Pandoc did not split exactly the manifest's chapters, parts and matter: "
                f"expected={len(desired)} unique={len(set(desired))} actual={len(references)} "
                f"unexpected={sorted(set(references) - set(desired))}")
        # Pandoc puts its TOC first when the automatic title page is disabled.
        # Keep the existing source title page first, followed by that single TOC.
        spine[:] = [references[identifier] for identifier in desired]
        for number, name in enumerate(figures):
            identifier = f"full-figure-{number}"
            ET.SubElement(package.find("o:manifest", NS), f"{{{OPF}}}item", {
                "id": identifier, "href": posixpath.relpath(name, posixpath.dirname(opf_path)),
                "media-type": "application/xhtml+xml",
            })
            ET.SubElement(spine, f"{{{OPF}}}itemref", {"idref": identifier, "linear": "no"})
        ET.register_namespace("", OPF)
        ET.register_namespace("dc", DC)
        entries[opf_path] = ET.tostring(package, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", entries.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for name, data in entries.items():
            archive.writestr(name, data)
    return fixed


def audit_epub(path, book, occurrences=None):
    language = book_language(book)
    entries = read_package(path)
    container = ET.fromstring(entries["META-INF/container.xml"])
    opf_path = container.find(".//{*}rootfile").get("full-path")
    package = ET.fromstring(entries[opf_path])
    require(package.get("version") == "3.0", "expected EPUB3 package")
    require(package.find("o:metadata/dc:language", NS).text == language,
            "incorrect book language")
    require(package.find("o:metadata/dc:title", NS).text == book.manifest["title"], "incorrect title")
    manifest = {}
    for item in package.findall("o:manifest/o:item", NS):
        name, _ = package_target(opf_path, item.get("href"))
        require(name in entries, f"missing manifest resource: {name}")
        require(not {"scripted", "remote-resources", "mathml"} & set(item.get("properties", "").split()),
                f"non-static EPUB resource: {name}")
        require(item.get("id") not in manifest, "duplicate manifest ID")
        manifest[item.get("id")] = name
    all_spine = [manifest[item.get("idref")] for item in package.findall("o:spine/o:itemref", NS)]
    spine = [manifest[item.get("idref")] for item in package.findall("o:spine/o:itemref", NS)
             if item.get("linear") != "no"]
    require(len(all_spine) == len(set(all_spine)), "duplicate spine documents")
    trees = {name: ET.fromstring(data) for name, data in entries.items() if name.endswith(".xhtml")}
    ids, global_ids, links, images, supplemental_images = {}, {}, [], Counter(), Counter()
    for name, tree in trees.items():
        require(tree.get("lang") == language and tree.get(XML_LANG) == language,
                f"incorrect XHTML language: {name}")
        ids[name] = set()
        for element in tree.iter():
            tag = element.tag.rsplit("}", 1)[-1]
            identifier = element.get("id")
            if identifier:
                require(identifier not in ids[name], f"duplicate XHTML ID: {name}#{identifier}")
                ids[name].add(identifier)
                global_ids.setdefault(identifier, []).append(name)
            require(tag not in {"script", "iframe", "object", "embed", "math"},
                    f"non-static XHTML: {name}: {tag}")
            for key, value in element.attrib.items():
                require(not key.lower().startswith("on") and key != "srcset",
                        f"active HTML attribute: {name}: {key}")
                if key == "style":
                    require(not re.search(r"@import|url\s*\(", value, re.I),
                            f"inline CSS resource dependencies are unsupported: {name}")
                if key not in {"href", "src", "poster", "data"}:
                    continue
                parsed = urlsplit(value)
                external = parsed.scheme or parsed.netloc
                if external:
                    require(tag == "a" and key == "href" and parsed.scheme in {"http", "https", "mailto"},
                            f"remote/active resource: {name}: {value}")
                    continue
                links.append((name, value))
            if tag == "img":
                require(element.get("alt", "").strip(), f"image lacks alternative text: {name}")
                classes = element.get("class", "").split()
                kind = next((c for c in classes if c in
                             {"inline-math", "display-math", "diagram", "diagram-detail", "full-formula"}), "source")
                (images if name in spine else supplemental_images)[kind] += 1
        for node in tree.findall(".//h:code", NS):
            require("mermaid" not in node.get("class", "").split(), "unconverted Mermaid code")
    for name, url in links:
        target, fragment = package_target(name, url)
        require(target in entries, f"missing EPUB link/resource: {name}: {url}")
        if fragment:
            require(fragment in ids.get(target, set()), f"missing EPUB fragment: {name}: {url}")
    for name, data in entries.items():
        require(not name.endswith(".svg"), f"SVG needs explicit offline static conversion: {name}")
        if name.endswith(".css"):
            css = data.decode("utf-8")
            require(not re.search(r"@import|url\s*\(", css, re.I),
                    f"CSS resource dependencies need explicit support: {name}")
    require(book.anchors <= global_ids.keys(), "EPUB lost expected book anchors")
    order = reading_order(book)
    files = []
    for identifier in order:
        require(len(global_ids[identifier]) == 1, f"non-unique stable book anchor: {identifier}")
        files.append(global_ids[identifier][0])
    require(len(files) == len(set(files)), "chapters must have separate XHTML documents")
    require(spine == files, "spine differs from manifest reading order")
    require(images["diagram-detail"] == 0 and supplemental_images["diagram-detail"] == 0,
            "cropped diagram panels are not supported in text or supplemental pages")
    nav_files = [name for name, tree in trees.items()
                 if tree.find(".//h:nav[@{http://www.idpf.org/2007/ops}type='toc']", NS) is not None]
    require(len(nav_files) == 1, "expected exactly one EPUB TOC")
    toc = trees[nav_files[0]].find(".//h:nav[@{http://www.idpf.org/2007/ops}type='toc']", NS)
    toc_targets = [package_target(nav_files[0], node.get("href"))
                   for node in toc.findall(".//h:a", NS)]
    require(all((global_ids[key][0], key) in toc_targets for key in order if key != "contents"),
            "native TOC does not cover every manifest entry")
    if occurrences is not None:
        for kind, image_class in (("inline", "inline-math"), ("display", "display-math"),
                                  ("mermaid", "diagram")):
            require(images[image_class] == occurrences.get(kind, 0),
                    f"{kind} coverage mismatch: {images[image_class]} != {occurrences.get(kind, 0)}")
    return {
        "chapters": book.manifest["chapter_count"], "parts": len(book.parts),
        "spine_documents": len(spine), "xhtml_documents": len(trees),
        "nonlinear_figure_documents": sum("/figures/figure-" in name for name in all_spine),
        "nonlinear_formula_documents": sum("/figures/formula-" in name for name in all_spine),
        "internal_links_and_resources": len(links), "image_occurrences": dict(images),
        "supplemental_image_occurrences": dict(supplemental_images),
        "packaged_image_assets": sum(name.endswith(".png") for name in entries),
        "language": language, "bytes": path.stat().st_size,
        "sha256": digest(path.read_bytes()), "errors": [],
    }


def publish_directory(staging, destination):
    backup = destination.with_name(destination.name + ".previous")
    require(not backup.exists(), f"previous build backup already exists: {backup}")
    had_previous = destination.exists()
    if had_previous:
        destination.rename(backup)
    try:
        staging.rename(destination)
    except OSError:
        if had_previous:
            backup.rename(destination)
        raise
    if had_previous:
        shutil.rmtree(backup)


def build(args):
    check_translation_sync(ROOT)
    book = Book(manifest=args.manifest, language=getattr(args, "language", None))
    language = book_language(book)
    destination = output_path(args.output or generated_dir(book.root, language) / "epub",
                              book.root, language)
    require(not any(inside(destination, book.root / source) for source in book.hashes),
            "output directory contains manuscript inputs")
    manuscript = book.assemble()
    require(PANDOC.is_file() and EPUBCHECK.is_file(),
            "missing pinned Pandoc/EPUBCheck; run python3 scripts/install_epub_tools.py")
    require(run([PANDOC, "--version"]).splitlines()[0] == "pandoc 3.6.4", "expected Pandoc 3.6.4")
    java = java_command()
    require("v5.2.1" in run([java, "-jar", EPUBCHECK, "--version"]), "expected EPUBCheck 5.2.1")
    require((EPUB_DIR / "node_modules/puppeteer/package.json").is_file(),
            "missing EPUB Node dependencies; run npm ci --prefix book/epub")
    destination.parent.mkdir(parents=True, exist_ok=True)
    cache = EPUB_DIR / ".cache/rendered"
    with tempfile.TemporaryDirectory(prefix=".epub-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "result"
        stage.mkdir()
        book.write(stage / "manuscript.md", manuscript)
        ast = json.loads(run([PANDOC, "--from=markdown-smart-implicit_figures", "--to=json"],
                             input=prepare_markdown(manuscript)))
        jobs, occurrences = prepare_ast(ast, book, stage)
        expected = source_counts(manuscript)
        require(all(occurrences.get(key, 0) == expected.get(key, 0)
                    for key in ("mermaid", "inline", "display")),
                f"Markdown/AST diagram or formula coverage differs: source={expected}, AST={occurrences}")
        request = Path(temporary) / "render-jobs.json"
        request.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        render_report = stage / "render.json"
        run(["node", EPUB_DIR / "render.mjs", request, cache, render_report], cwd=EPUB_DIR)
        rendered = json.loads(render_report.read_text(encoding="utf-8"))
        (stage / "rendered").mkdir()
        ast = apply_images(ast, rendered, language)
        for item in rendered["results"]:
            shutil.copyfile(cache / item["file"], stage / "rendered" / item["file"])
        ast_path = Path(temporary) / "book.json"
        ast_path.write_text(json.dumps(ast, ensure_ascii=False), encoding="utf-8")
        epub = stage / f"ai-engineering-interview-{language}.epub"
        run([PANDOC, ast_path, "--from=json", "--to=epub3", "--standalone",
             "--epub-title-page=false", "--split-level=2", "--toc", "--toc-depth=2", "--no-highlight",
             "--data-dir", EPUB_DIR, "--css", EPUB_DIR / "epub.css",
             "--resource-path", stage, "--output", epub],
            cwd=stage)
        resource_hashes = {item.relative_to(stage).as_posix(): digest(item.read_bytes())
                           for folder in ("rendered", "assets")
                           for item in (stage / folder).rglob("*") if item.is_file()}
        repaired = repair_links(epub, resource_hashes, book)
        report = audit_epub(epub, book, occurrences)
        check_report = stage / "epubcheck.json"
        try:
            check_log = run([java, "-jar", EPUBCHECK, epub, "--json", check_report])
        except BookError as error:
            if check_report.is_file():
                messages = json.loads(check_report.read_text(encoding="utf-8")).get("messages", [])
                print(json.dumps(messages[:10], ensure_ascii=False, indent=2), file=sys.stderr)
            raise error
        (stage / "epubcheck.txt").write_text(check_log, encoding="utf-8")
        check = json.loads(check_report.read_text(encoding="utf-8"))
        require(not any(message.get("severity") in {"ERROR", "FATAL", "WARNING"}
                        for message in check.get("messages", [])), "EPUBCheck reported errors/warnings")
        report.update({
            "builder": "build_epub.py", "pandoc": "3.6.4", "epubcheck": "5.2.1",
            "git_commit": run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
            "source_receipt": "manuscript.build.json", "occurrences": occurrences,
            "unique_rendered": dict(Counter(item["kind"] for item in rendered["results"])),
            "repaired_internal_links": repaired, "renderer": rendered["version"],
            "epubcheck_errors": 0, "epubcheck_warnings": 0,
            "kindle_previewer": "not performed", "kdp_acceptance": "not claimed",
            "diagram_limits_css_px": {"width": 480, "height": 650},
            "diagram_detail_tiles": 0,
        })
        (stage / "build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
        # Sources, including assets, must remain byte-for-byte unchanged.
        require(all(digest((ROOT / name).read_bytes()) == checksum for name, checksum in book.hashes.items()),
                "manuscript sources changed during export; retry from a stable revision")
        publish_directory(stage, destination)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"EPUB: {destination / epub.name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_language_arguments(parser)
    parser.add_argument("--output", type=Path,
                        help="dedicated output directory (default: book/<language>/generated/epub), "
                             "replaced only after successful validation")
    args = parser.parse_args(argv)
    try:
        build(args)
        return 0
    except (BookError, InstallError, OSError, UnicodeError, json.JSONDecodeError,
            ET.ParseError, zipfile.BadZipFile) as error:
        print(f"epub: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
