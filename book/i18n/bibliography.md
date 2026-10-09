# Maintaining the shared bibliography

The website and EPUB use the same `docs/book/references.md` and `references.zh.md` backmatter. Inline citations use ordinary Markdown links inside `<sup>`, for example:

```markdown
The paper’s result<sup>[【15】](../../book/references.md#ref-15)</sup>
```

Use `references.zh.md` in Chinese chapters, with the same number. Entries have explicit `<a id="ref-15"></a>` anchors rather than headings, so references do not become hundreds of contents entries. `scripts/build_book.py` accepts these anchors only in the `references` manifest document, validates uniqueness, and resolves them when assembling the book.

## Sources of truth

`book/bibliography.json` stores stable consecutive numbers, exact source URLs, original linked titles, and the complete relocated source notes in both languages. The numbered entry identifies a URL; the reading notes retain original author/title spellings, versions, dates, access limitations, licensing statements, and the scope of each source’s use. Distinct URLs, including versioned specification URLs, pinned commits, and fragments, remain distinct: do not merge them merely because their titles look similar.

The paired bibliography Markdown pages are generated from the registry. Edit source-note prose or bibliographic titles in the registry, then regenerate; do not maintain an independent hand-edited copy in the generated pages. A missing localized proper source title may retain its original spelling; that is not permission to replace Chinese explanatory prose with English.

## Migration and maintenance

```bash
# Read-only inventory and exact source hashes.
python3 scripts/migrate_bibliography.py --report .artifacts/bibliography-review.json

# Parse both editions first, then write the registry, bibliography, and citation edits.
python3 scripts/migrate_bibliography.py --apply --report .artifacts/bibliography-review.json
```

Run against current source files, never copy old chapter snapshots over newer edits. The tool checks that source bytes have not changed since reading before it writes. It recognizes only the explicit, known trailing source headings, preserves chapter headings and footer/navigation notices, and uses the shared Markdown link parser to protect examples, code, math, comments, images, and YAML metadata. A dry run is the default.

For a new source, put an explicit link beside the relevant claim in both source chapters, then run the tool. New URLs append to the registry; existing numbers never change. To add only general further reading, edit the relevant chapter’s paired `notes` in the registry instead. Never infer a paragraph-to-source relationship from an old chapter-end list. Review generated changes before recording translation synchronization. The report’s English paths and hashes identify mechanically processed sources, not proof of semantic or factual review.

The retained chapter-end heading links to its source notes with `#reading-<stable-chapter-id>`. Old links to that heading remain valid. Source-note prose links to other local chapters are rebased to the bibliography’s directory, preserving their targets.

## Validation

Run `python3 scripts/migrate_bibliography.py --check` to reject stale generated pages or unmigrated source links, and `python3 -m unittest discover -s scripts/tests -p test_bibliography.py` for regressions. Also run the existing documentation, translation synchronization, localized-link, strict site, both-language book, and EPUB regression checks before publication. Verify rendered superscripts and bibliography targets in the website and EPUB; valid source syntax alone is not visual acceptance.

Both `.github/workflows/docs.yml` and `.github/workflows/epub.yml` run the read-only bibliography freshness check before publication builds. Their path filters cover the registry, source pages, migration script, and shared link parser. The check does not regenerate files or record translation synchronization in CI.
