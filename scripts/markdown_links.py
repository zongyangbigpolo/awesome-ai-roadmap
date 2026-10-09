"""Lossless Markdown link destination editing, using only the Python stdlib.

Callbacks receive the source spelling of a URL (including escapes/entities), not
its decoded value. Delimiters, labels, titles and all other source text stay put.
Unsupported or malformed link syntax raises MarkdownLinkError before callbacks
run, so callers never receive a silently incomplete rewrite.
"""

from collections.abc import Callable
import html
import re


class MarkdownLinkError(ValueError):
    """Markdown cannot be inspected or rewritten without losing information."""


_ESCAPABLE = r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~"""
_REFERENCE = re.compile(r"\[((?:\\.|[^\[\]\\\r\n])+)\]:")
_TAG = re.compile(r"</?([A-Za-z][A-Za-z0-9-]*)(?=[\s/>])")
_ATTRIBUTE = re.compile(
    r"""([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?"""
)


def markup_url(raw):
    """Decode markup for lookup and retain source offsets for lossless URL edits."""
    characters, offsets = [], []
    position = 0
    while position < len(raw):
        end = position + 1
        value = raw[position]
        if value == "\\" and raw[end:end + 1] and raw[end:end + 1] in _ESCAPABLE:
            value = raw[end]
            end += 1
        elif value == "&":
            entity = re.match(r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);", raw[position:])
            if entity:
                end = position + entity.end()
                value = html.unescape(entity[0])
        characters.extend(value)
        offsets.extend([position] * len(value))
        position = end
    return "".join(characters), offsets


def language_switch_target(source: str, label: str | None) -> str | None:
    """Resolve a plain inline language label to this page's exact companion."""
    if label is None:
        return None
    if source.endswith(".zh.md"):
        return source[:-6] + ".md" if label.strip().casefold() == "english" else None
    if source.endswith(".md") and label.strip() == "简体中文":
        return source[:-3] + ".zh.md"
    return None


def is_language_switch(source: str, target: str, label: str | None) -> bool:
    expected = language_switch_target(source, label)
    return expected is not None and target == expected


def _escaped(text, position):
    start = position
    while start and text[start - 1] == "\\":
        start -= 1
    return (position - start) % 2 == 1


def _quote_prefix(line):
    position, depth = 0, 0
    while match := re.match(r" {0,3}>[ \t]?", line[position:]):
        position += match.end()
        depth += 1
    return position, depth


def _boundary(body):
    return bool(re.match(r"#{1,6}\s|`{3,}|~{3,}|\$\$|<!--", body)
                or re.fullmatch(r"(?:\* *){3,}|(?:- *){3,}|(?:_ *){3,}", body))


class _Context:
    """Indentation is relative to the current list/blockquote container."""

    def __init__(self):
        self.columns = []
        self.paragraph = False
        self.quote_depth = 0

    def line(self, line):
        prefix, depth = _quote_prefix(line)
        if depth != self.quote_depth:
            self.columns = []
            self.paragraph = False
            self.quote_depth = depth
        value = line[prefix:].rstrip("\r\n")
        whitespace = len(value) - len(value.lstrip(" \t"))
        indent = len(value[:whitespace].expandtabs(4))
        body = value[whitespace:]
        offset = prefix + whitespace
        if not body:
            self.paragraph = False
            return offset, 0, 0, False, depth
        marker = None if _boundary(body) else re.match(r"([-+*]|\d{1,9}[.)])([ \t]+|$)", body)
        if marker or _boundary(body) or not self.paragraph:
            while self.columns and indent < self.columns[-1]:
                self.columns.pop()
        base = self.columns[-1] if self.columns else 0
        relative = max(0, indent - base)
        if marker and relative <= 3:
            padding = len(marker[2].expandtabs(4))
            used = len(marker[2]) if 1 <= padding <= 4 else min(1, len(marker[2]))
            offset += len(marker[1]) + used
            base = indent + len(marker[1]) + (padding if 1 <= padding <= 4 else 1)
            self.columns.append(base)
            rest = line[offset:].rstrip("\r\n")
            spaces = len(rest) - len(rest.lstrip(" \t"))
            relative = len(rest[:spaces].expandtabs(4))
            offset += spaces
            body = rest[spaces:]
            self.paragraph = False
        code = relative >= 4 and not self.paragraph
        self.paragraph = bool(body) and not code and not _boundary(body)
        return offset, base, relative, code, depth


class _Links:
    def __init__(self, text, path):
        self.text = text
        self.path = path
        self.spans = []
        self.labels = {}
        self.inline_links = {}

    def error(self, position, message):
        line = self.text.count("\n", 0, position) + 1
        raise MarkdownLinkError(f"{self.path}:{line}: {message}")

    def whitespace(self, position):
        start = position
        while position < len(self.text) and self.text[position] in " \t\r\n":
            position += 1
        if re.search(r"\n[ \t\r]*\n", self.text[start:position]):
            self.error(start, "blank line in Markdown link")
        return position

    def title(self, position):
        opener = self.text[position]
        closer = ")" if opener == "(" else opener
        start = position
        position += 1
        while position < len(self.text):
            char = self.text[position]
            if char == "\\" and position + 1 < len(self.text):
                position += 2
                continue
            if char == closer:
                if re.search(r"\n[ \t\r]*\n", self.text[start:position]):
                    self.error(start, "blank line in link title")
                return position + 1
            if opener == "(" and char == "(":
                self.error(position, "nested parentheses in link title")
            position += 1
        self.error(start, "unclosed link title")

    def destination(self, position, reference=False):
        """Return the URL span and the end of its complete link suffix."""
        start = self.whitespace(position)
        position = start
        angle = self.text[position:position + 1] == "<"
        if angle:
            start = position = position + 1
        depth = 0
        # An empty destination followed by a title needs separating whitespace.
        empty_with_title = (not reference and not angle and
                            self.text[start:start + 1] in ("\"", "'") and
                            start > 0 and self.text[start - 1].isspace())
        if not empty_with_title:
            while position < len(self.text):
                char = self.text[position]
                if char == "\\" and position + 1 < len(self.text):
                    position += 2
                    continue
                if angle:
                    if char == ">":
                        break
                    if char in "\r\n<":
                        self.error(position, "malformed angle-bracket link destination")
                else:
                    if char.isspace() or (char == ")" and depth == 0):
                        break
                    if char == "<":
                        self.error(position, "unescaped '<' in link destination")
                    if char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                position += 1
        end = position
        if angle:
            if self.text[position:position + 1] != ">":
                self.error(start, "unclosed angle-bracket link destination")
            position += 1
        if depth:
            self.error(start, "unbalanced parentheses in link destination")
        if reference and start == end:
            self.error(start, "empty reference destination")
        after_url = position
        if reference:
            line_end = self.text.find("\n", position)
            line_end = len(self.text) if line_end == -1 else line_end
            tail = position
            while tail < line_end and self.text[tail] in " \t\r":
                tail += 1
            if tail == line_end and line_end < len(self.text):
                candidate = line_end + 1
                while candidate < len(self.text) and self.text[candidate] in " \t":
                    candidate += 1
                if self.text[candidate:candidate + 1] in ('"', "'", "("):
                    tail = candidate
        else:
            tail = self.whitespace(position)
        if (tail > after_url or empty_with_title) and self.text[tail:tail + 1] in ('"', "'", "("):
            position = self.title(tail)
            if reference:
                end_of_line = self.text.find("\n", position)
                end_of_line = len(self.text) if end_of_line == -1 else end_of_line
                if self.text[position:end_of_line].strip():
                    self.error(position, "malformed reference definition suffix")
                return start, end, end_of_line
            position = self.whitespace(position)
        elif reference:
            end_of_line = self.text.find("\n", after_url)
            end_of_line = len(self.text) if end_of_line == -1 else end_of_line
            if self.text[after_url:end_of_line].strip():
                self.error(after_url, "malformed reference definition suffix")
            return start, end, end_of_line
        else:
            position = tail
        if self.text[position:position + 1] != ")":
            self.error(position, "malformed or unclosed inline link")
        return start, end, position + 1

    def fence(self, start, end, body, base, depth):
        match = re.match(r"(`{3,}|~{3,})", body)
        if match and match[1][0] == "`" and "`" in body[match.end():]:
            self.error(start, "backtick in code fence info string")
        delimiter = re.escape(match[1][0]) + "{" + str(len(match[1])) + ",}"
        closing = re.compile(delimiter + r"[ \t]*$")
        position = end
        while position < len(self.text):
            stop = self.text.find("\n", position)
            stop = len(self.text) if stop == -1 else stop + 1
            line = self.text[position:stop].rstrip("\r\n")
            prefix, quote_depth = _quote_prefix(line)
            rest = line[prefix:]
            spaces = len(rest) - len(rest.lstrip(" \t"))
            indent = len(rest[:spaces].expandtabs(4))
            if quote_depth == depth and base <= indent <= base + 3 and closing.fullmatch(rest[spaces:]):
                return stop
            position = stop
        self.error(start, "unclosed code fence")

    def html(self, position):
        tag = _TAG.match(self.text, position)
        if not tag:
            return None
        quote = None
        end = tag.end()
        while end < len(self.text):
            char = self.text[end]
            if quote:
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == ">":
                break
            end += 1
        if end == len(self.text):
            self.error(position, "unclosed HTML tag")
        if not self.text.startswith("</", position):
            for attribute in _ATTRIBUTE.finditer(self.text, tag.end(), end):
                if attribute[1].lower() == "href":
                    value = next((index for index in (2, 3, 4) if attribute[index] is not None), None)
                    if value is None:
                        self.error(attribute.start(), "HTML href has no destination")
                    self.spans.append(attribute.span(value))
            if tag[1].lower() in ("pre", "code", "script", "style", "textarea"):
                close = re.search(r"</" + re.escape(tag[1]) + r"\s*>", self.text[end + 1:], re.I)
                if not close:
                    self.error(position, f"unclosed HTML {tag[1]} block")
                return end + 1 + close.end()
        return end + 1

    def parse(self):
        text = self.text
        if "\x00" in text:
            self.error(text.index("\x00"), "NUL is not valid in Markdown input")
        position = 1 if text.startswith("\ufeff") else 0
        front = re.match(r"---[ \t]*\r?\n", text[position:])
        if front:
            close = re.search(r"^(?:---|\.\.\.)[ \t]*\r?$", text[position + front.end():], re.M)
            if close is None:
                self.error(position, "unclosed YAML front matter")
            position += front.end() + close.end()
        context = _Context()
        brackets = []
        while position < len(text):
            if position == 0 or text[position - 1] == "\n" or (position == 1 and text[0] == "\ufeff"):
                stop = text.find("\n", position)
                stop = len(text) if stop == -1 else stop + 1
                offset, base, relative, code, depth = context.line(text[position:stop])
                body = text[position + offset:stop].rstrip("\r\n")
                if not body:
                    brackets.clear()
                if code:
                    brackets.clear()
                    position = stop
                    continue
                if relative <= 3 and re.match(r"`{3,}|~{3,}", body):
                    brackets.clear()
                    position = self.fence(position, stop, body, base, depth)
                    context.paragraph = False
                    continue
                definition = _REFERENCE.match(text, position + offset)
                if definition and not definition[1].startswith("^"):
                    start, end, position = self.destination(definition.end(), reference=True)
                    self.spans.append((start, end))
                    brackets.clear()
                    context.paragraph = False
                    continue
            if text.startswith("<!--", position):
                end = text.find("-->", position + 4)
                if end == -1:
                    self.error(position, "unclosed HTML comment")
                position = end + 3
                continue
            if text[position] == "`":
                run = re.match(r"`+", text[position:])[0]
                closing = re.search(r"(?<!`)" + re.escape(run) + r"(?!`)", text[position + len(run):])
                if closing:
                    content = text[position + len(run):position + len(run) + closing.start()]
                    if (re.search(r"\n[ \t\r]*\n", content) or
                            re.search(r"\n {0,3}(?:`{3,}|~{3,}|#{1,6}[ \t])", content)):
                        closing = None
                if closing:
                    position += len(run) + closing.end()
                else:
                    position += len(run)
                continue
            if text.startswith(("$$", r"\[", r"\("), position):
                opener = text[position:position + 2]
                closer = {"$$": "$$", r"\[": r"\]", r"\(": r"\)"}[opener]
                end = text.find(closer, position + 2)
                while end != -1 and _escaped(text, end):
                    end = text.find(closer, end + len(closer))
                if end == -1 and opener == "$$":
                    self.error(position, "unclosed math expression")
                if end != -1:
                    position = end + len(closer)
                    continue
            if text[position] == "$":
                end = text.find("$", position + 1)
                line_end = text.find("\n", position)
                while end != -1 and _escaped(text, end):
                    end = text.find("$", end + 1)
                if end != -1 and (line_end == -1 or end < line_end):
                    position = end + 1
                    continue
            if text[position] == "\\" and text[position + 1:position + 2] in _ESCAPABLE:
                position += 2
                continue
            if text[position] == "<":
                end = self.html(position)
                if end is not None:
                    position = end
                    continue
                autolink = re.match(r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*|[^\s<>@]+@[^\s<>@]+)>",
                                    text[position:])
                if autolink:
                    self.spans.append((position + 1, position + autolink.end() - 1))
                    position += autolink.end()
                    continue
            if text[position] == "[":
                brackets.append(position)
            elif text[position] == "]" and brackets:
                opening = brackets.pop()
                if text[position + 1:position + 2] == "(":
                    label = text[opening + 1:position]
                    image = opening > 0 and text[opening - 1] == "!" and not _escaped(text, opening - 1)
                    start, end, position = self.destination(position + 2)
                    self.spans.append((start, end))
                    if not image:
                        self.labels[(start, end)] = label
                        self.inline_links[(start, end)] = (opening, position)
                    continue
            position += 1
        return sorted(self.spans)


def rewrite_labeled_links(
    text: str, path: str, rewrite: Callable[[str, str | None], str],
) -> str:
    """Rewrite URL tokens with their raw inline label, or None for other syntax.

    ``path`` is used only for diagnostics. The callback receives raw source URL
    text, without ``<...>`` or HTML attribute quotes. Code, math, comments and
    YAML front matter are excluded. Parsing finishes before callbacks execute.
    """
    links = _Links(text, path)
    spans = links.parse()
    pieces, position = [], 0
    for start, end in spans:
        replacement = rewrite(text[start:end], links.labels.get((start, end)))
        if not isinstance(replacement, str):
            raise MarkdownLinkError(f"{path}: link callback must return a string")
        pieces.extend((text[position:start], replacement))
        position = end
    pieces.append(text[position:])
    return "".join(pieces)


def rewrite_inline_links(text: str, path: str, rewrite: Callable[[str, str, str], str]) -> str:
    """Replace complete inline links, never images, examples or reference definitions.

    The callback receives the raw destination, label and complete original link.
    The existing parser validates the whole input before any callback executes.
    """
    links = _Links(text, path)
    spans = links.parse()
    pieces, position = [], 0
    for start, end in spans:
        if (start, end) not in links.inline_links:
            continue
        opening, closing = links.inline_links[(start, end)]
        replacement = rewrite(text[start:end], links.labels[(start, end)], text[opening:closing])
        if not isinstance(replacement, str):
            raise MarkdownLinkError(f"{path}: link callback must return a string")
        pieces.extend((text[position:opening], replacement))
        position = closing
    pieces.append(text[position:])
    return "".join(pieces)


def rewrite_links(text: str, path: str, rewrite: Callable[[str], str]) -> str:
    """Rewrite actual URL tokens, preserving every other source character."""
    return rewrite_labeled_links(text, path, lambda url, label: rewrite(url))


def labeled_link_destinations(text: str, path: str) -> list[tuple[str, str | None]]:
    """Return raw URL tokens and inline labels; references/HTML/images have no label."""
    links = _Links(text, path)
    return [(text[start:end], links.labels.get((start, end)))
            for start, end in links.parse()]


def link_destinations(text: str, path: str) -> list[str]:
    """Return destination tokens in source order, with escapes left intact."""
    return [url for url, _ in labeled_link_destinations(text, path)]
