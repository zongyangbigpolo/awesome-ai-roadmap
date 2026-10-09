---
description: Examine multimodal benchmark contamination, visual threat models, content credentials, and watermarking, distinguishing media-feature caches, prefix KV caches, and disaggregated serving.
---

# Chapter 10: Multimodal Evaluation, Safety, and Inference Serving

> [LLM · Multimodal Models, Sections 23.5–23.6](../../llm/06-multimodal/23-multimodal-models.md) provides the overall framework for evaluation, safety, and deployment: perception/reasoning/robustness/safety dimensions, encode–decode costs, and media-input limits. Rather than repeat it, this chapter develops three specific issues: benchmark contamination and updates, attacks and provenance mechanisms particular to images and generated content, and architectural practices for inference serving.

## 10.1 How can we distinguish improved multimodal ability from benchmark contamination?

Scores alone cannot make that distinction. Combine source provenance, near-duplicate checks, and holdout sets excluded from training and tuning. Input perturbations can aid diagnosis, but one score drop does not prove the model memorized test questions.

Multimodal benchmarks—especially those built from web images and public question banks—face **contamination** similar to text-only benchmarks, but harder to detect. If benchmark images and their question–answer pairs appear in crawled pretraining data, a model may remember answers rather than possess the tested ability, inflating scores. Image near-duplicates at different resolutions, with different crops, or with watermarks are harder to find through simple hashing than verbatim text duplicates.

Mitigations include genuinely newly collected, nonpublic holdouts, perceptual image deduplication and text matching, source grouping, and regular updates. **A benchmark release after the training cutoff does not establish that its source material was unseen**: old textbook images and answers may be repackaged and republished. Dates are even less conclusive when the cutoff is unknown or the model is continuously updated.

MMMU targets multidisciplinary academic knowledge, while MathVista targets mathematical reasoning in visual contexts. Neither is a dynamic benchmark, and difficult questions do not inherently prevent contamination: complex questions and solutions can also be memorized. Controls such as image substitution, numerical perturbation, and evidence masking can help, but a performance drop is a diagnostic signal, not standalone proof. Report the model/API version, prompt template, image budget, tool permissions, and sample confidence intervals to distinguish data issues from differences in inference budgets.

## 10.2 Image-specific adversarial and safety risks

Beyond indirect prompt injection discussed in [LLM, Section 23.6](../../llm/06-multimodal/23-multimodal-models.md), image input introduces two more specific attack surfaces:

- **Typographic attacks** add text labels that conflict with an image's subject and may bias CLIP-style classifiers toward the written concept. The original research analyzes this through experiments including zero-shot classification and linear probes. Success depends on the image, text, and candidate classes; arbitrary added text does not necessarily change classification. This reflects competition between visual content and textual cues, not necessarily a model executing malicious written instructions.
- **Visual jailbreaks**: published work constructs visual adversarial examples that cause aligned models to violate safety policies under particular model-access and optimization settings. Whether perturbations are hard to perceive, require gradients, or transfer to other models depends on the threat model. White-box experiments do not establish the same bypass for arbitrary black-box products. Nor can failure be attributed only to insufficient visual-alignment data; visual representations, cross-modal interfaces, and generation policies may all contribute.

Safety evaluation should cover visual and audio channels, distinguishing semantic confusion from text embedded in an image, indirect prompt injection in screenshots, and optimized adversarial perturbations. Report attacker permissions, perturbation constraints, request counts, target models, and false-refusal rates on normal inputs. Results for one attack type do not replace testing another threat.

## 10.3 Provenance and labeling of generated content

The image and video generators in [Chapters 7 and 8](../04-generation/README.md) create new provenance problems: generated media and real recordings may be difficult to distinguish visually. Two main approaches are used:

- **Content Credentials / C2PA** binds provenance and editing assertions to media assets with digital signatures. Verifiers check the binding, signature, and trust in the issuer. This can establish that an issuer made an assertion and whether the associated content was altered. It does not establish the truth of events depicted or guarantee a complete editing history. The fixed version 2.1 specification is cited here as a conceptual basis, not as the latest version.
- **Invisible watermarking** embeds markers directly in generated pixels or time-domain signals, imperceptible to people but recognizable by dedicated detectors. Google DeepMind's SynthID, for example, has been used in image and video generation products, aiming to retain detection of generated origin after common edits such as compression or cropping.

These approaches complement one another. Credentials verify provenance assertions; watermark detection identifies a marker within a particular generator–detector system. Credentials can become detached from files, and editing can damage watermarks. Neither is an absolute guarantee. **Missing credentials or an undetected watermark do not prove real capture.** Positive detections also need interpretation alongside false-positive rates, confidence, and processing history.

## 10.4 Inference serving: encoding and decoding have different resource profiles

Multimodal input adds media decoding, preprocessing, and modality encoding, but the bottleneck depends on the request. High-resolution input with a short answer may be encode/prefill-bound; long answers may be autoregressive-decode-bound. Measure these stages separately rather than assume encoding is always the bottleneck:

- **Schedule by actual work**: text already varies in length, while media adds decoded dimensions, frame counts, and tile counts. Compressed file size is not a reliable proxy for visual tokens. Limit decoded pixels, frames, duration, and output budgets; bucket requests by encoding work and total tokens so large requests do not delay smaller ones in the same batch.
- **Separate three computations**: media encoding, language-model prefill, and language-model decode are distinct stages. Media encoding produces features; prefill produces language KV states. They should not be collapsed into a single “encoding stage.” DistServe studies prefill/decode disaggregation for text LLMs, not direct evidence of benefits from separating multimodal encoders. Disaggregation may reduce resource contention, but feature/KV transfer, queuing, and poor utilization at low load can offset the gains. Validate on target workloads using time to first token (TTFT), average time per output token after the first (TPOT), and goodput under latency constraints.
- **Feature caching is not KV caching**: identical media with the same encoder and preprocessing can reuse encoded features. Cache keys should include a media-content hash, model/adapter version, crop settings, and sampling parameters. Language-model KV states also depend on the complete prefix, positions, attention masks, and model configuration. Identical images do not justify reusing that segment's language KV when preceding system prompts or text change. If a fixed shared prefix precedes the question, use prefix caching rather than splice media KV into arbitrary contexts.

Caches also need tenant isolation, permission checks, capacity limits, and expiry policies to prevent sensitive media from being reused across users or retained indefinitely. Streaming audio and incremental video are not one-off encoding costs; continuously arriving media need a separate budget. Load-test before optimizing the architecture, comparing P95 latency, timeout rate, peak GPU memory, and per-request cost across resolutions, frame counts, answer lengths, and concurrency levels.

## 10.5 Common mistakes

### 10.5.1 Equating higher benchmark scores with genuine capability gains

Scores may change because of capability, leakage, prompts, or test-time compute budgets. Check original sources and near-duplicates, not just benchmark release dates. When training data is unknown, state that contamination cannot be ruled out rather than asserting that it must have occurred.

### 10.5.2 Red-teaming only text input

Text-only tests do not cover visual perturbations, text in images, or spoken instructions. These risks may nevertheless share mechanisms with text instruction-following failures. Test combinations of channels rather than assume vulnerabilities in different modalities are entirely independent.

### 10.5.3 Treating watermarks or content credentials as unbreakable guarantees

Cropping, compression, and re-encoding affect the two mechanisms differently. A watermark signal may weaken; a signature binding may fail verification or require an editor to issue new credentials while preserving the provenance chain. Failed signature verification does not directly mean the content is false, and no promise should be made that all generated content is detectable.

### 10.5.4 Reusing text-only batching policies unchanged for multimodal requests

Ignoring media-dependent encoding loads lets large-media requests delay others in the same batch. Redesign batching and scheduling around the different resource profiles in Section 10.4.

## 10.6 Chapter summary

1. Benchmark release dates differ from source-material dates. Combine holdouts, near-duplicate detection, and input controls to assess contamination risk.
2. Image inputs introduce attack surfaces such as typographic attacks and visual jailbreaks that text-only safety tests do not cover; visual and audio channels need explicit red-team coverage.
3. C2PA content credentials and invisible watermarks such as SynthID are complementary engineering approaches to provenance, but neither is absolutely reliable.
4. Measure media encoding, language prefill, and decode separately. Feature caching and prefix KV caching have different reuse conditions, and disaggregation needs workload-based validation.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-10) for this chapter’s sources, reading suggestions, and source notes.
