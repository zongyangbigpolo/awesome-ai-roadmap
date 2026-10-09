# Maintaining the bilingual handbook

English is the primary manuscript and the default reading language. Simplified Chinese is a complete companion edition, not a set of summaries.

## Content and sources

Use the existing Chinese manuscript to preserve the scope, examples, assumptions, and level of detail. Check technical meaning against the original papers, specifications, and official documentation cited by the chapter. A model's recollection does not override either source.

Keep historical claims tied to their stated version. Do not silently replace a documented interface with the latest one, invent unavailable source details, or claim to have run an experiment that was not run. Record conflicts and the evidence used to resolve them.

See [Maintaining the shared bibliography](bibliography.md) ([简体中文](bibliography.zh.md)) for stable citation numbers, paired source notes, lossless migration, and the shared website/EPUB citation syntax.

Write idiomatic technical English rather than translating Chinese sentence structure word for word. Answer the actual question, explain the mechanism, and introduce limitations where they affect the argument. Preserve useful examples and derivations; do not replace a full section with a summary.

## File and edition contract

- `docs/<topic>/<module>/<chapter>.md` is the English source.
- Its Chinese companion is `<chapter>.zh.md` in the same directory.
- The same convention applies to topic/module indexes and reader-facing front and back matter: `README.md` and `README.zh.md`.
- English chapters use `# Chapter N: Title`. Both languages retain the existing chapter numbers and numbered section hierarchy.
- Existing unprefixed website routes serve the English edition; Chinese counterparts are under `/zh/`. Language switching must retain the logical chapter rather than return to the home page.
- English source links target the normal `.md` files. Chinese source links target the corresponding `.zh.md` files, except for external references and intentionally language-independent assets.
- The book manifests are `book/en/manifest.json` and `book/zh-CN/manifest.json`. Both use the same logical chapter IDs and reading order, with localized source paths, titles, and metadata.
- Both website and EPUB are built from these source files. Do not maintain separate web and EPUB prose or commit generated books.

The migration covers all 143 knowledge chapters and their reader-facing indexes and supporting pages. Missing translations must fail validation; a Chinese fallback must not masquerade as an English page or an English EPUB.

## Preserve meaning in examples

Translate diagram labels, captions, headings, and explanatory code comments. Preserve API identifiers, protocol field names, numerical examples, units, time zones, formulas, and executable behavior. Chinese text that is itself example data may remain, with an English explanation where needed.

Do not turn fictional cases into the author's work history. Do not add contributors, project results, quotations, or performance claims. Keep technical sources close to their claims and general attribution in the existing closing matter.

Use `glossary.json` as a guide, not a mechanical replacement dictionary. In particular, distinguish reasoning from model inference, retrieval from recall, and runtime state from an audit record.

## English-first changes

Start a content change in English. In the same PR, update the affected Chinese companion or explicitly review why an English-only wording change leaves the Chinese meaning unchanged. Contributors should not have to open a second content PR for the other language.

The synchronization record identifies the source and translation revisions that were reviewed together. Updating a hash is not proof of a good translation: never refresh records merely to silence a stale-translation error. The English manuscript, Chinese companion, and cited sources still need editorial review.

Do not translate the entire book on every site build or translate pages in a reader's browser. No external translation service, API key, or paid request is introduced implicitly. A writing agent may prepare the companion update in the PR; CI checks coverage and synchronization, then builds the two language editions.

## Review evidence

The initial migration keeps per-scope records in `reviews/`. Each record identifies the original source revision, the paired pages, the source material actually checked, and any unresolved limitations. Existing `book/reviews/` files remain historical records of the earlier Chinese technical review, not claims that the English edition was already reviewed at that time.

EPUB metadata must describe the actual language. English format support does not replace Kindle Previewer, rights, accessibility, and publication checks; Simplified Chinese must not be mislabeled as Traditional Chinese or English.
