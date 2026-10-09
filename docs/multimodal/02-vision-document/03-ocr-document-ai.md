---
description: Explain the differences between OCR, layout-aware models, and OCR-free document understanding, including table structure, field validation, error attribution, and cloud-service selection.
---

# Chapter 3: OCR and Document AI

> For the engineering decision between an OCR pipeline and page-screenshot retrieval in RAG, see [RAG · Document Parsing, Section 3.5](../../rag/02-ingestion-indexing/03-document-parsing.md). This chapter focuses on OCR/Document AI **models themselves**: architectural development, coordinate outputs, and evaluation metrics. The chapters complement one another without repeating each other's scope.

## 3.1 Why is recognizing the text not enough to understand a document?

A classic OCR pipeline performs **text detection** and **text recognition**, but boxes and strings only locate and transcribe text. They do not guarantee correct reading order or structure on a scanned page. Invoices, contracts, forms, and financial reports also require identifying headings, amount columns, and the values associated with particular labels. Document AI therefore extends transcription to key–value pairs, tables, and layout structure. When a digital PDF already has a reliable text layer, evaluate direct extraction before defaulting to another OCR pass.

## 3.2 Layout-aware models: the LayoutLM family

The central idea of LayoutLM is to expose the model to **text content, two-dimensional coordinates, and visual features**, rather than just a text sequence. LayoutLM adds 2D position embeddings to BERT-style pretraining, supplying each text token's bounding-box coordinates as extra input. LayoutLMv3 further unifies text and image-patch processing: the same Transformer receives text tokens and image patches, with cross-modal alignment pretraining objectives such as determining whether the image patch corresponding to a text token has been masked.

Two-dimensional coordinates help distinguish relationships such as “same row,” “same column,” and “next to the label,” reducing the information lost when a page is flattened into a text sequence. However, the LayoutLM family does not automatically produce the correct reading order. It still receives an OCR token sequence and often needs dedicated layout analysis, ordering, or relationship-prediction modules. Coordinate embeddings alone also do not eliminate sequence truncation, incorrect boxes, or cross-page field association problems.

## 3.3 OCR-free end-to-end document understanding

Text-driven LayoutLM extraction still relies on OCR text and coordinates. Donut uses a vision encoder and autoregressive text decoder, removing the separate OCR engine at inference time. Pretraining learns to generate text sequences from document images, with synthetic documents among its data sources. Downstream fine-tuning then produces serialized structural results that are parsed into JSON. “OCR-free” therefore means neither “does not learn text recognition” nor “needs no transcription supervision during training.”

OCR-free models remove error propagation across a separate OCR interface but can still omit characters, miscopy numbers, or fill nonexistent fields from language priors. Jointly optimizing recognition and extraction is an advantage; reduced explicit evidence, long-output decoding costs, and generalization to unfamiliar layouts are tradeoffs. For auditing, require page numbers and evidence regions, then verify against the original image or independent OCR. Format constraints can make JSON parseable, not make its values correct.

## 3.4 Tables and charts: structure matters more than text alone

Tables and charts are among the most underestimated tasks in document intelligence. Accuracy depends not just on recognizing text but on **recovering structure**.

- **Table structure recognition** must recover rows, columns, headers, and relationships across cells. TATR uses DETR-style models for table detection and structure recognition separately, then combines row/column regions and text into cells through postprocessing. The detection head itself does not transcribe all text. Work accompanying PubTables-1M uses **GriTS** to measure table-grid structure, location, or content. Another common metric, **TEDS**, comes from PubTabNet and represents an HTML table as a tree. Its standard version considers both structure and cell text; it is not a pure structure score. Specify a structure-only variant when comparing topology alone.
- **Chart understanding** is different: the text in a bar or line chart often consists only of axis labels and legends, while the actual information lies in visual encodings such as bar height, line slope, and color groups. Benchmarks such as ChartQA require combining these encodings with chart text to answer numerical questions like “哪一年增长最快” (“Which year had the fastest growth?”). Failure modes differ substantially from plain OCR: a model may read every axis label correctly yet misread the relative heights of the bars.

## 3.5 Coordinates and layout-box representations

Document models can generate coordinates or predict regions with detection heads, as in [Chapter 2](02-vlm-grounding.md). They can also reuse input OCR boxes and predict only field labels, entity relationships, or segmentation masks. Document structure additionally requires a page → paragraph → line → word hierarchy. Multi-page output should include page numbers, coordinate scales, and field evidence so boxes at identical positions on two pages are not mistaken for the same entity.

## 3.6 Production services: not every use case needs an in-house model

Cloud services are candidate baselines for common receipts, invoices, and identity documents, but **model versioning, prediction confidence, and availability SLAs do not guarantee business-field accuracy**. Pin API or processor versions and validate on your own document distribution:

| Service | Role |
|---|---|
| Azure AI Document Intelligence | Prebuilt models for invoices, receipts, and identity documents, plus trainable custom extraction models |
| Google Document AI | Specialized processors such as form parsers and invoice parsers |
| Amazon Textract | Text detection and document analysis APIs; forms and tables can be selected in the same document analysis request |

Selection also depends on language and regional-format support, data residency, log retention, page limits, throughput, and per-page cost. Even with prebuilt models, calibrate confidence thresholds according to field risk. Route low-confidence results to human review, and still check high-confidence amounts against business constraints such as totals, currency, and dates. Estimate missed errors and review costs on an independent validation set; model confidence is not automatically a calibrated probability of correctness.

For example, synchronous Textract `AnalyzeDocument` uses `FeatureTypes` to select analysis types such as `FORMS` and `TABLES` together, returning blocks and their relationships. Asynchronous analysis uses `StartDocumentAnalysis`. Different structural tasks do not necessarily require separate interfaces.

## 3.7 Evaluation: measure layers, not just an overall score

| Layer | Metrics | Meaning |
|---|---|---|
| Character/word recognition | CER (character error rate), WER (word error rate) | Text recognition accuracy without structure |
| Layout structure | Reading-order accuracy, region-classification F1 | Correct identification of paragraphs, headings, headers, footers, and other regions |
| Table structure and content | TEDS and GriTS, with variants specified | Standard TEDS is affected by text; distinguish structure, location, and content |
| Key–value extraction | Field-level precision/recall/F1 | Whether fields such as invoice amount and invoice date are extracted correctly and completely |
| End-to-end document QA | ANLS (average normalized Levenshtein similarity) | Benchmarks such as DocVQA evaluate answers through string similarity |

Low CER or WER does not establish downstream usability: correct recognition of large amounts of body text can hide a single wrong digit in an amount. ANLS tolerates some string edits and should not be the sole criterion for monetary correctness. Fix normalization rules for dates, spaces, and amount formats, then separately report exact match on critical fields and the proportion of documents with every critical field correct.

Controlled comparisons help locate errors. Substitute ground-truth text and boxes into an OCR pipeline and see whether extraction scores recover. If they do, recognition or localization is the main bottleneck; otherwise, inspect reading order, relationship reasoning, and field definitions. OCR-free systems can also compare high-resolution local crops with the original page to distinguish insufficient resolution from structural-understanding failures.

## 3.8 Common mistakes

### 3.8.1 Treating overall OCR accuracy as document-understanding ability

High character-recognition accuracy does not establish correct layout, table topology, or critical-field extraction. Evaluate each layer as described in Section 3.7.

### 3.8.2 Flattening tables into plain text before extraction

Turning table rows into one continuous text passage loses relationships across rows and columns. Questions involving numerical comparisons or conditional filtering should preserve a structured representation; see the table-evidence principles in [RAG · Multimodal RAG, Section 21.3](../../rag/04-advanced/21-multimodal-rag.md).

### 3.8.3 Ignoring scan quality, rotation, and multilingual content

Production documents commonly include skew, low-resolution scans, obscuring stamps, and mixed languages. High benchmark scores do not directly transfer to these conditions; validate them separately using samples from the real distribution before deployment.

## 3.9 Chapter summary

1. Document AI targets structured understanding, not just text recognition. Layout, tables, and key–value relationships are central to evaluation and architecture.
2. LayoutLM uses 2D coordinates and visual signals to support structural understanding, without automatically guaranteeing correct reading order.
3. Donut needs no separate OCR engine but still learns text recognition and can make perceptual errors or hallucinate.
4. Table structure and content, chart visual encodings, and text recognition have different failure modes and need separate evaluation.
5. Compare cloud services and in-house solutions on the same business data. Model confidence cannot replace field validation and human review.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-03) for this chapter’s sources, reading suggestions, and source notes.
