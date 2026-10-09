# Maintaining and publishing the bilingual book

[简体中文](README.zh.md)

This guide is for authors and maintainers, not part of the reader manuscript. Readers can start at the [book contents](../docs/book/README.md) and use the website's language switcher for the corresponding Chinese page. English is the primary manuscript; Chinese is a complete companion, not a summary. Each language uses the **same Markdown sources for its website and reflowable EPUB3**, with no separate EPUB prose.

The book covers all 143 knowledge chapters. **Release validation requires two complete EPUBs built from synchronized, complete sources.** Small bilingual test books can verify the export pipeline but cannot establish that the full English book has been built or reviewed.

## One source per language, two reading formats

English sources use `docs/<topic>/<NN-module>/NN-chapter.md`; complete Chinese companions use sibling `NN-chapter.zh.md` files. The convention also applies to indexes and front/back matter. English occupies the website root, Chinese `/zh/`; switching languages should retain the logical page. Internal source links stay within their language, apart from shared assets and external references. Export does not translate, rewrite the prose, or convert Simplified to Traditional Chinese.

[`en/manifest.json`](en/manifest.json) and [`zh-CN/manifest.json`](zh-CN/manifest.json) share 143 stable knowledge-chapter IDs, nine parts, and their reading order. Titles are **AI Engineering Interviews: From Model Foundations to Field Delivery** and **AI 工程面试：从模型原理到现场交付**. Part titles, source paths, and metadata are localized. Websites retain module navigation; books follow the explicit manifest order.

The nine parts contain: LLMs 23 chapters, multimodal AI 10, tools and protocols 15, RAG 22, agents 25, frameworks and orchestration 23, production engineering 13, safety and governance 10, and FDE 2. Original chapter numbers ascend within each part, restarting at 1. English source headings use `# Chapter N: Title`; both languages keep the same numbered section hierarchy. Assembled headings show the full position, such as “Part 1, Chapter 1”; export does not globally renumber sections or references such as “Chapter 14.”

Manifests store part titles and stable chapter IDs/paths; knowledge-chapter titles come from source H1 headings. `front_matter` and `back_matter` select each language's title page, preface, reading guide, acknowledgments, author, and license pages under `docs/book/`. Scripts generate the reader indexes; do not maintain a second handwritten list of 143 titles.

## Daily editing and assembly

Start edits in English and update the Chinese companion **in the same PR**. If an English-only wording change leaves the Chinese meaning intact, explicitly review that decision. Preserve the original Chinese material's explanations, assumptions, examples, and technical depth; check claims against cited primary sources. Keep API identifiers, numerical examples, formulas, and version qualifications intact; translate explanatory comments and diagram labels without changing executable behavior.

Maintenance order: update the real English and Chinese sources, including Chinese links to `.zh.md` companions; regenerate both reader indexes; record the pairs actually reviewed; then run strict checks and build both editions. Assembly uses only the Python 3.10+ standard library. From the repository root:

```bash
# After editing both sources, regenerate and commit both reader indexes.
# Standalone index maintenance does not require current synchronization records.
python3 scripts/build_book.py --language en --write-index
python3 scripts/build_book.py --language zh-CN --write-index

# Record genuinely reviewed pairs here, using --record / --record-all as explained below.
# Then run the read-only synchronization check; ROOT is the repository root.
python3 scripts/check_translations.py --root .

# Validate both editions without generating manuscripts.
python3 scripts/build_book.py --language en --check
python3 scripts/build_book.py --language zh-CN --check

# CI also rejects stale reader indexes.
python3 scripts/build_book.py --language en --check --check-index
python3 scripts/build_book.py --language zh-CN --check --check-index

# Assemble manuscripts and traceable build records; the default language is English.
python3 scripts/build_book.py
python3 scripts/build_book.py --language zh-CN

python3 -m unittest discover -s scripts/tests -p 'test_build_book.py'
```

Standalone `build_book.py --language LANG --write-index`, without `--check` or `--output`, maintains source indexes: it validates manifests and sources but does not require current synchronization records. Every `--check`, normal manuscript assembly, EPUB export, and `--write-index` combined with `--output` must first pass `scripts/check_translations.py --root ROOT`. Missing companions, stale synchronization records, or an absent checker **fail these strict commands**; there is no fallback, relabeling, or publishing skip flag.

The synchronization checker's default mode is read-only. After generating both indexes and completing actual editorial review, run it with `--record PATH.md ... --note "Describe the review actually performed"` for the selected pairs. During migration, `--record-all --note "Describe the review actually performed"` requires review of the entire covered set. Replace the example note with the review actually performed; never refresh hashes just to silence an error. Isolated `Book` parser fixtures may test parsing without the synchronization gate; release commands may not bypass it. No automatic or paid translation service, API key, browser translation, or whole-book translation at build time is introduced.

Both CLIs accept `--language en|zh-CN`, defaulting to `en`. The advanced alternative `--manifest book/zh-CN/manifest.json` selects a repository-relative manifest and infers its language from metadata; it is **mutually exclusive** with `--language`. Language, source-path suffixes, H1 conventions, and the title-page H1 must agree. Both canonical manifests and their paired source files are required, even when building one edition. Discovery checks each language's knowledge chapters exactly once, not 286 files as a single edition. Missing chapters, duplicate IDs/paths, invalid JSON fields, incorrect order or H1 numbers, escaping paths, missing assets, and broken fragments fail validation. Do not skip bad files to make a build pass.

Outputs are `book/en/generated/manuscript.md` and `book/zh-CN/generated/manuscript.md`, with `manuscript.build.json` and, when needed, an adjacent `assets/` directory. Successful checks identify the language and report `chapters=143 parts=9` for that edition. Generated directories are ignored; do not commit assembled prose. `--output FILE` can select an external destination, with assets alongside it; inside the repository, output must stay in the selected language's generated directory and never overwrite sources or the other edition. `--check` cannot accompany `--output`. Standalone `--write-index` writes only `docs/book/README.md` or `docs/book/README.zh.md`, not a manuscript.

When adding, moving, or removing a chapter, update both manifests, paired sources, all relevant website indexes, and MkDocs navigation, then regenerate both book indexes. Regenerate after title review too. Before publishing, also run `python3 scripts/check_docs.py`, `npm run check:mermaid`, and `.venv/bin/mkdocs build --strict`. Assembly is not a substitute for chapter-by-chapter technical review.

## Conversion boundaries

| Input | Treatment in the assembled manuscript |
|---|---|
| YAML page metadata | Strip only the initial paired `---` block; do not insert descriptions into the prose |
| Links to included chapters and front/back matter | Rewrite to stable anchors in one manuscript; validate original heading fragments before mapping |
| Website-wide and topic indexes | Map to the book contents or corresponding part; do not concatenate website index prose |
| Module indexes and other excluded Markdown pages | Validate, then form full online links under `source_url`, preserving the intended module; **requires a network connection**, not a substitute chapter |
| Local images and other non-Markdown attachments | Check existence and repository containment, then copy to adjacent `assets/`, preserving repository-relative hierarchy to avoid collisions |
| External references and remote images | Preserve URLs without downloading; remote images are not yet offline publication assets |
| Reference-style links | Rewrite definition targets and namespace labels by chapter to prevent cross-chapter collisions |
| Fenced/inline/indented code and math | Preserve source; do not rewrite example links, comments, or headings inside them as prose |
| Editorial HTML comments | Omit from the reader manuscript; preserve comments inside code examples |
| Recognized repeated author footers and website-return lines | Remove only known patterns, not technical qualifications, source notes, or specific third-party attribution |

This assembler handles the repository's Markdown subset, not all of CommonMark or EPUB. It supports ordinary inline links, including parenthesized URLs, angle-bracket destinations and optional same-line titles, standard reference links, and quoted HTML `href`/`src`. Unsupported footnotes, custom source HTML anchors, and `srcset` fail explicitly. Add conversions and regression cases before using them; new block syntax or multiline links also need tests, not merely a successful exit code.

Part anchors look like `part-agent`, chapters like `agent-24`, and numbered sections like `agent-24-s24-2`. Unnumbered headings use chapter-local sequential IDs, such as `agent-24-extra-01`. Localized heading fragments map to these anchors. Renaming a title does not change chapter or numbered-section IDs; renumbering sections or reordering unnumbered headings requires a cross-reference review.

The earlier review removed generic author footers from chapter sources; compatibility handling for older formats does not change the repository license. Unrecognized chapter-author declarations cause an error rather than a guessed deletion. Keep specific third-party credits, papers, and specifications beside their arguments; general attribution and licensing belong in `docs/book/colophon.md` and `docs/book/colophon.zh.md`.

## Edition records and terminology

`schema_version` identifies the manifest format. `edition` is an internal manuscript revision, not a published edition or ISBN. Freeze each edition with its Git commit, manifest/source hashes, review records, and `manuscript_sha256`. Identical inputs should yield identical manuscript bytes; update internal revision metadata when changing the manuscript and retain earlier build records.

Chapter IDs identify the same material across languages, regardless of translated titles, moves, or display order. Record the Chinese source revision used for migration and the paired revisions actually reviewed; do not fork a generated Chinese manuscript into an independently maintained English book. Previous Chinese review records are not evidence that the English translation was reviewed.

Use a glossary keyed by stable concept IDs, recording Chinese wording, preferred English terms, retained abbreviations, semantic notes, and the first chapter ID. Resolve context before unifying “memory,” “context,” “state,” “retrieval,” or “tool execution.” Preserve product names, API identifiers, and necessary version limits; a shared translation must not erase distinct concepts. A glossary or hash record alone does not establish completed terminology or translation review.

## EPUB export and downloads

The website retains `.github/workflows/docs.yml`; EPUB uses the independent [Build EPUB](https://github.com/zongyangbigpolo/awesome-ai-roadmap/actions/workflows/epub.yml) workflow. Its `en`/`zh-CN` matrix builds PR previews, relevant `main` updates, and manual runs. It has read-only repository permissions: no Release, website deployment, or KDP upload. Website deployment does not depend on EPUB export succeeding.

One content PR updates both language sources; website and EPUB checks consume those same files and run independently after merge. There is no separate “EPUB content PR” and no manually maintained or committed `.epub`. Successful full-book artifacts require complete, synchronized sources; sample books cannot replace full exports.

Download `ai-engineering-interview-en-epub` or `ai-engineering-interview-zh-CN-epub` from a successful run's **Artifacts**. Each contains its corresponding `ai-engineering-interview-en.epub` or `ai-engineering-interview-zh-CN.epub`, `build.json`, manuscript hashes, static-render records, and EPUBCheck reports. Downloads generally require GitHub sign-in. Retention is 90 days, possibly shortened by repository/organization policy; an authorized maintainer can use **Run workflow** to rebuild expired artifacts.

### Local tools and export

Full export supports macOS arm64/x64 and Linux x64, with Python 3.10+, Node.js **22**, and separately installed Java 17+. The installer does not change global PATH, install Java, or modify another main checkout. Windows users can use an x64 Linux environment. Although the pinned Pandoc archives include Linux arm64, the bundled Puppeteer Chromium does not support that platform; use an x64 runner rather than claiming full Linux arm64 support.

```bash
# First installation, or after pinned dependency versions change.
python3 scripts/install_epub_tools.py
npm ci --prefix book/epub

# Assembly, static rendering, packaging, link audit, and EPUBCheck.
python3 scripts/build_epub.py
python3 scripts/build_epub.py --language zh-CN
```

Default files are `book/en/generated/epub/ai-engineering-interview-en.epub` and `book/zh-CN/generated/epub/ai-engineering-interview-zh-CN.epub`. Intermediate manuscripts, `rendered/` PNGs, and build records remain alongside them for review. `--output DIRECTORY` selects a dedicated destination, subject to source and language isolation; only this tool's existing output can be replaced. All checks must pass before replacing the last successful export. Missing tools/assets, unknown formulas, rendering errors, or write failures fail the build rather than produce a book with missing illustrations.

Pandoc **3.6.4** and EPUBCheck **5.2.1** install into `book/epub/.tools/` after full-archive SHA-256 verification against [`epub/tools.json`](epub/tools.json). These hashes were obtained from official GitHub Release downloads over HTTPS; they are not upstream signatures. The isolated `book/epub/package-lock.json` pins Mermaid **11.12.0**, MathJax **3.2.2**, Puppeteer **24.15.0**, and Noto Sans SC **5.2.5**. Chromium uses `book/epub/.cache/puppeteer/`; ordinary website `npm ci` does not install these dependencies. Initial tool/font downloads need a network connection, but manuscript conversion never sends content to a remote rendering service.

For missing Linux Chromium libraries, follow the distribution-specific [Puppeteer troubleshooting guidance](https://pptr.dev/troubleshooting); disabling the sandbox is not a library fix. Local rendering enables the browser sandbox. Only an isolated, disposable CI runner should explicitly set `EPUB_NO_SANDBOX=1`.

### Preserving the reading experience

Export reuses `scripts/build_book.py` validation, ordering, stable IDs, links, and attribution handling, then parses Markdown into a Pandoc AST. Fenced, inline, and indented code are not formulas; Mermaid inside example code is not an illustration. Independent source-segment counts must agree with AST diagram/formula counts. Unsupported structures need explicit conversions and regression tests, not relaxed counting.

Each knowledge chapter, part page, and front/back matter page becomes XHTML; the manifest determines the linear spine. Keep the source title page, not Pandoc's automatic one, and replace manuscript contents with a single native EPUB navigation tree. Original within-part chapter numbers remain; stable chapter/section IDs transfer to headings. After packaging, repair cross-file links using actual XHTML IDs and resource hashes, then verify every destination. External references remain clickable online, but **prose, diagrams, and formulas require no network access or scripts**.

Keep Mermaid and LaTeX in each language's source; render that language's labels locally to PNG with alternative text only during export. A single browser batches rendering with isolated renderers and fonts, blocks external addresses, and caches by language, content, renderer, and lockfile. Images use double pixel density and white backgrounds so black text does not disappear in dark reading modes. Inline formulas have preferred widths in `em`, shrink proportionally within cells/paragraphs, and do not widen the page. A formula links to its complete image on a separate page and back to the exact occurrence without discarding source pixels. The Chinese font supports rendered images; it does not lock the ebook's body font.

Ordinary source images currently support local PNG/JPEG/GIF. Remote images, dependency-bearing SVG, embedded Mermaid images/icons, and interactive links require explicit offline static conversion first; export rejects them rather than fetching or silently removing content.

The main text shows a diagram overview and a localized detail link. A separate, nonlinear page contains the full image and overlapping detail tiles ordered left-to-right, then top-to-bottom; content beyond a screen edge is not discarded. Every occurrence has its own detail page and precise backlink, while reused PNGs are packaged once. Detail pages do not enter the chapter contents or linear reading sequence; tiles do not clutter the main text. Explicit renderer dimension/area limits fail the build, requiring a diagram adjustment rather than silent omission or an unreadable thumbnail. CSS visually wraps code without inserting newlines into its content. Tables with four or more columns display each row as labeled fields at viewport widths of 600px or less; larger screens retain the table. Labels come from the localized column headings, and cell content, code, and links remain intact. Merged cells, multiple header rows, and image-only or empty headings in these wide tables need explicit export support. Tables, large diagrams, and formulas still need device review, including readers that do not apply these media queries.

An empty top-left header is supported when that column contains row names: these names remain visible without an invented field label. Other empty column headings fail export.

All generated navigation, detail-page labels, and backlinks use the selected language, as do EPUB/XHTML language metadata. EPUB-only CSS lives in `book/epub/epub.css` and does not override website styles. Export creates no cover or invented ISBN/publisher; the bibliographic author remains Polo Li and licensing stays in closing matter. Changing metadata alone never makes a Chinese source an English edition.

### Regression tests and acceptance

Regression coverage must distinguish source-index maintenance from publishing: standalone `--write-index` can regenerate indexes before synchronization is recorded, but stale/missing records or a missing checker must still fail `--check`, assembly, EPUB export, and `--write-index --output`. The maintenance path still rejects invalid manifests, source paths, and H1 headings; it is not a way to publish incomplete translations.

```bash
# Unit tests need neither export tools nor a browser.
python3 -B -m unittest discover -s scripts/tests -p 'test_*.py'

# Real rendering and small English/Chinese integration books: no skipped tool checks.
npm test --prefix book/epub
python3 -B scripts/tests/epub_integration.py

# Final integration, after all translations pass synchronization: both full 143-chapter books.
python3 scripts/build_epub.py --language en
EPUB_LANGUAGE=en npm run test:layout --prefix book/epub
python3 scripts/build_epub.py --language zh-CN
EPUB_LANGUAGE=zh-CN npm run test:layout --prefix book/epub
```

Small integration books must use real Pandoc, browser rendering, and EPUBCheck in both languages; missing tools are failures, not skipped success. They do not replace the two full exports above, which require every translated source to be present. `EPUB_LANGUAGE` defaults to `en`; layout tests must inspect the requested edition, not a fallback.

`build.json` distinguishes diagram/formula **occurrences**, deduplicated renders, detail tiles, and packaged assets, recording byte counts, SHA-256, chapters, parts, spine, internal-link checks, and tool versions. `manuscript.build.json` records source and asset hashes; `render.json` locates PNGs and dimensions; `epubcheck.json` / `.txt` preserve official validation results. Full export also checks mimetype, OPF, language, navigation, all internal fragments, resource integrity, scripts, and remote dependencies. Publish artifacts only after error-free diagram/formula processing and EPUBCheck with no errors or warnings.

Browser layout regression opens representative pages from the actual selected EPUB, including quantization formula tables and the five-column agent building-block comparison, at 375px width and 16/24/32px font sizes. It checks horizontal overflow, formula aspect ratios, unclipped code, and formula-page backlinks, plus wide-table field labels at 375px and their hidden state at 768px, producing `layout.json` with the EPUB hash and per-page measurements for CI artifacts. This is not manual layout acceptance: inspect language-appropriate fonts, narrow-screen code/tables, font sizes, portrait/landscape, dark mode, and every diagram/formula in ebook readers and Kindle Previewer. Export records retain explicit statements that Kindle Previewer manual review was not performed and KDP acceptance is not claimed.

## Publication limits and author decisions

**Format support, preview acceptance, and distribution eligibility are separate.** KDP accepts EPUB conforming to its Kindle Publishing Guidelines and recommends Kindle Previewer before upload. Passing EPUBCheck establishes only the EPUB requirements it checks, not visual acceptance, KDP acceptance, or language eligibility.

**Simplified Chinese remains a language restriction.** The recorded KDP list includes `Chinese (Traditional) (eBook only)`, not Simplified Chinese, and warns that unsupported-language ebooks may be removed. Keep the complete Simplified Chinese edition, but do not call it directly KDP-ready or mislabel it as Traditional Chinese or English. A genuine English manuscript addresses the source-language distinction; it does not bypass preview, rights, or platform review. Do not convert to Traditional Chinese without an author decision.

**Disclose AI content according to how it was produced.** KDP requires disclosure of AI-generated text, images, or translations, even after substantial human editing. Editing, polishing, or checking human-created work with AI can instead fall under the corresponding AI-assisted category. Record the actual process for each content type and follow the current submission requirements; human review does not automatically turn generated content into human-authored content.

**Ordinary KDP publication is not KDP Select.** The terms' Optional Programs → KDP Select → Exclusivity section requires digital exclusivity during enrollment. This book's full text has been public on GitHub/Wiki under CC BY 4.0; do not automatically enroll in Select or Kindle Unlimited. The author must separately determine whether exclusivity can be satisfied. Removing copyright notices or closing the repository does not revoke CC licenses already granted.

**Respect the limits of the available rights.** Authors may commercially publish their original work but cannot revoke existing CC BY 4.0 grants. Third-party papers, code, screenshots, trademarks, and quotations have their own rights and licenses; review their actual final use rather than assuming an open repository permits unrestricted reprinting. A centralized license page does not replace required third-party credits, notices, or permissions.

## What remains before distribution

Complete technical and translation review, synchronize both editions, and freeze a revision. Build and validate **both complete 143-chapter EPUBs**, not just fixtures. Static illustrations, formulas, native navigation, and reflowable packaging still need manual checks of diagram text, mathematical meaning, alternative text, wide tables, code, and asset rights.

Use Kindle Previewer across screen sizes, font sizes, and orientations; inspect every diagram and formula, not only structural reports. With a genuine supported-language manuscript, cover, bibliographic details, truthful acknowledgments, and rights review in place, fill out KDP using the actual publication language and AI production history. Do not invent ISBNs, publishers, publication years/editions, or contributor names to fill a page.

### Publication references and checking dates

These are retained policy checks, **not new research**: EPUB format/language support was checked on **2026-09-18**; other publication rules retain the **2026-09-15** record. Recheck the primary pages before release; platform rules change.

- KDP [Supported eBook Formats](https://kdp.amazon.com/en_US/help/topic/G200634390).
- KDP [Book Supported Languages](https://kdp.amazon.com/en_US/help/topic/G200673300).
- KDP [Content Guidelines](https://kdp.amazon.com/en_US/help/topic/G200672390).
- KDP [Terms and Conditions](https://kdp.amazon.com/en_US/terms-and-conditions), whose recorded page update was **2024-09-27**.
