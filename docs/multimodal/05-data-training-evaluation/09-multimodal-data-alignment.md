---
description: Examine image–text filtering, synthetic captions, interleaved documents, and factually augmented preference alignment, including validation of sampling mixtures, leakage, and filtering bias.
---

# Chapter 9: Multimodal Training Data and Alignment

> This chapter examines how data coverage, filtering, and training objectives affect multimodal capabilities. “Quality matters more than quantity” is not a law that needs no experiment. For the overall training framework, see [LLM · Multimodal Models](../../llm/06-multimodal/23-multimodal-models.md); for general RLHF and DPO principles, see [LLM · Training and Alignment](../../llm/02-training-alignment/README.md).

## 9.1 What data does each training objective need?

Contrastive and generative pretraining are different objectives; not every model goes through both in sequence. Instruction tuning and preference alignment can also be omitted or alternated. Data requirements depend on frozen modules, target tasks, and the existing base model. There is no mandatory example count for each stage:

| Objective | Example structure | Sources | Key quality requirements |
|---|---|---|---|
| Contrastive representation learning | Positive pairs and sampled negative pairs | Web data, licensed data, dedicated collection | Relevant positive pairs, controlled false negatives, long-tail coverage |
| Generative pretraining | Image–text pairs, interleaved sequences, or audio/video sequences | Web documents, synthetic captions, licensed media | Consistent conditions and targets, correct spatial/temporal alignment and sequence boundaries |
| Instruction tuning | Media, instructions, answers, and optional evidence | Synthetic data and human annotations | Answers supported by inputs, sufficient task and format coverage |
| Preference alignment | Candidate answers and preferences for the same input | Human or model-assisted comparisons | Distinguish factuality, helpfulness, and safety; control length bias |

Data, representation resolution, model capacity, compute budgets, and optimization jointly constrain results. More data cannot recover tiny text lost during input compression, and higher resolution cannot replace task supervision entirely absent from training.

## 9.2 Large-scale image–text pairs: sources and noise

LAION-5B is a historical example of a dataset built by extracting image links and associated text from Common Crawl and filtering with CLIP similarity. It primarily distributes an index of URLs, text, and metadata—not redistribution or training authorization for every image. Broken links, changed source content, and unclear rights affect reproducibility and compliance. Alt text can also contain navigation terms, SEO text, or incomplete descriptions. Appearing on the same web page does not establish reliable semantic alignment.

## 9.3 Quality filtering and synthetic captions

Common ways to improve pretraining data include:

- **Similarity filtering** can reduce mismatches, but a CLIP score is not the probability that a pair is correct. It may favor common objects, languages, and styles, incorrectly removing specialist charts, OCR examples, or long-tail categories. Set thresholds through stratified inspection of the target data rather than assuming higher is always better.
- **Deduplication and splitting** should combine content hashes, perceptual features, and text deduplication. Group by original document, video, speaker, or source before dividing into training, validation, and test sets. Adjacent video frames or different crops of the same page must not be randomly placed on opposite sides of a split; near-duplicate leakage inflates scores.
- **Synthetic or regenerated captions**: the DALL·E 3 report studies mixtures of synthetic and original captions rather than guaranteeing that replacing everything is optimal. Detailed captions can add subject relationships but also introduce captioner hallucinations. Retain provenance and original text, inspect counts, text, and relationships closely, and compare mixture ratios.
- **Safety and compliance filtering** must remove illegal or high-risk material, including child sexual abuse material (CSAM) and nonconsensual private content, as well as material outside the scope permitted by licenses and copyright. This is a required compliance step in the data pipeline, not an optional enhancement.

## 9.4 Building multimodal instruction-tuning data

Pretraining and instruction tuning do not divide capabilities into rigid categories. The former provides image–text associations and a foundation for task abilities; the latter uses instruction examples to adjust problem handling, output behavior, and evidence use. Original LLaVA demonstrates a scalable instruction-data construction method: text-only GPT-4 generates conversations, detailed descriptions, and complex reasoning examples from human captions and object boxes for COCO images. This reduces the need to write each conversation manually but still reuses human image annotations. GPT-4 does not see the images directly, so synthetic examples are limited by annotation completeness and accuracy.

Entirely model-generated instruction data can amplify annotation bias or invent incorrect details. It needs human spot checks and targeted additions for weak tasks such as counting, spatial relationships, and OCR. Include unanswerable cases too: “目标不存在” (“the target is absent”), “图像太模糊” (“the image is too blurry”), or “两张图无法确定是同一人” (“the two images do not establish that this is the same person”). Otherwise the model may learn to invent a complete answer for every input.

A useful control keeps the question but replaces or masks the media. If answers barely change and still score highly, the data may let the model rely on language priors rather than visual evidence. Negative examples also need human verification so “not annotated” is not mistaken for “not present.”

## 9.5 Interleaved image–text data and in-context learning

Instruction tuning can include single-turn, multi-turn, and multi-image tasks; it is not limited to a single turn. **Interleaved image–text documents** preserve the order and relationships of images and text within a document. Flamingo and OBELICS/original IDEFICS demonstrate the value of this organization for multi-image context tasks. It is an important source, but not the only way to obtain that supervision: constructed multi-image comparisons, sequences of demonstrations, and multi-turn data can provide corresponding supervision too. Increasing the number of independent image–text pairs alone does not guarantee coverage of cross-image relationships.

Concatenation must also define image boundaries, paragraph association, and visibility masks. Arbitrarily shuffling web-page order can associate a question with the wrong image. Mixture sampling should not track example counts alone: a video clip or high-resolution document page may consume many more tokens and compute. Record each task's sampling probability, effective tokens, loss weight, and training time to prevent long-sequence modalities from dominating gradients. Retain text replay and modality-specific validation sets to check whether adding vision training harms existing language abilities.

## 9.6 Multimodal preference alignment

Multimodal preference judgments must separate factual consistency from response style. LLaVA-RLHF's factually augmented reward model uses extra image captions, ground-truth answer options, and other information to aid judgment. Its purpose is to reduce reward hacking, not to provide an automatic fact verifier. Incomplete annotations can still cause correct details to be penalized.

With DPO, preferred and dispreferred answers should address **the same media and the same question**; otherwise the preference difference may reflect input difficulty rather than answer quality. Construct candidates with similar length and tone but different factual content, then check whether rewards are genuinely sensitive to spatial, counting, or text errors. Measure refusal rates as well: a model might lower hallucinations by always saying “无法判断” (“cannot determine”), at the expense of helpfulness.

## 9.7 Common mistakes

### 9.7.1 Looking only at scale, not image–text matching quality

It is not valid to claim that strict filtering and an order-of-magnitude reduction in data must improve results. Compare filtering strengths under equal training-compute budgets and report long-tail, language, and task slices separately. Overfiltering may improve the average score while discarding the difficult examples you most need.

### 9.7.2 Expecting paired image–text data alone to cover multi-image and in-context learning

If training uses only independent image–text pairs, explicitly test cross-image comparison, changes in image order, references, and learning from demonstrations. A single-image VQA score cannot stand in for them. Interleaved web pages are one supplement; multi-image instructions and verified synthetic sequences also provide training signals.

### 9.7.3 Applying generic preference data directly to multimodal alignment

Text-oriented judgments such as “which answer is more detailed or helpful?” can encourage longer answers with invented details. Multimodal preference collection should explicitly include factual-consistency checks, as discussed in Section 9.6.

## 9.8 Chapter summary

1. There is no universal recipe for training stages or data scale. Match them to objectives, the existing model, frozen parameters, and compute budgets.
2. Design image–text filtering, deduplication, and compliance review around the sources. Synthetic captions are an optional enhancement whose gains and biases both need validation.
3. Text-only models can synthesize multimodal instruction data from structured annotations, but human review and targeted supplements for weak tasks remain necessary.
4. Interleaved documents and multi-image instructions supervise cross-image relationships. More independent image–text pairs cannot replace evaluation of those tasks.
5. Multimodal preference alignment needs explicit factual-consistency checks to prevent reward models from encouraging detailed but hallucinated answers.

> Validate data changes on an independent test set under equal compute budgets. Changing filtering, sampling ratios, and training steps together makes it difficult to identify which change produced the gains.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-09) for this chapter’s sources, reading suggestions, and source notes.
