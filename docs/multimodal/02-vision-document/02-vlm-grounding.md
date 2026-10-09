---
description: Distinguish visual question answering, referring expression comprehension, and open-vocabulary detection, covering coordinate protocols, negative examples, localization evaluation, and resolution tradeoffs.
---

# Chapter 2: Vision–Language Models and Visual Grounding

> In this chapter, “grounding” specifically means **visual localization**: mapping a linguistic reference such as “左上角的红色按钮” (“the red button in the upper-left corner”) to coordinates or a region in an image. This differs from grounding an answer in verifiable evidence in RAG; see [RAG · Multimodal RAG, Section 21.5](../../rag/04-advanced/21-multimodal-rag.md). General multimodal architectures and training are covered in [Chapter 1](../01-foundations/01-multimodal-fusion-architecture.md) and [LLM · Multimodal Models](../../llm/06-multimodal/23-multimodal-models.md). Here we focus on visual understanding and localization.

## 2.1 The spectrum of VLM capabilities

A vision–language model (VLM) may look like a system that simply answers questions about images. Its capabilities can be separated into a spectrum from coarse to fine:

| Capability | Output | Representative task |
|---|---|---|
| Image captioning | Natural language | Describe an entire image in one sentence |
| Visual question answering (VQA) | Natural language | Answer open-ended questions about image content |
| Referring expression comprehension | Coordinates or regions | Locate the region corresponding to “图中戴帽子的人” (“the person wearing a hat in the image”) |
| Open-vocabulary detection | Multiple sets of coordinates and classes | Specify categories through text queries and attempt transfer to categories not used as fixed training labels |
| Grounded segmentation | Segmentation masks | Locate at the pixel level rather than with rectangles |

This is not a ranking in which each capability necessarily includes the previous ones. Detection returns multiple boxes, segmentation returns masks, and VQA can also involve spatial reasoning. The distinction is whether the task requires **verifiable spatial correspondences**. Grounding is not limited to language models generating coordinates; dedicated detectors and segmenters can also do it.

## 2.2 How does a language model “say” coordinates?

An autoregressive language model generates token sequences. There are two common approaches to obtaining bounding boxes:

1. **Coordinate serialization**: the original Qwen-VL paper normalizes coordinates to $[0,1000)$ and represents boxes as numeric text with special boundary markers, such as `<box>(102,304),(560,812)</box>`. PaliGemma instead quantizes normalized coordinates into 1024 dedicated location tokens in the order `ymin, xmin, ymax, xmax`; it does not directly generate decimal numbers in the same format. Both use autoregressive generation, but their coordinate order, vocabulary, and quantization rules are not interchangeable.
2. **Language-conditioned detectors**: a detection head outputs boxes and matching scores while a text encoder represents the query. No generative LLM is required afterward. Grounding DINO tightly fuses image and text information during feature enhancement, query selection, and cross-modal decoding; vision and language are not “loosely coupled.”

Serialization makes it convenient to unify conversation and structured output, but long lists introduce generation latency, invalid formats, and quantization error. Detectors are better suited to generating candidate boxes in parallel, though they still need threshold selection, deduplication, and phrase matching. Multi-turn reference resolution also requires conversational state; the presence or absence of a detection head alone does not establish that capability.

Bounding-box overlap is commonly measured using **intersection over union (IoU)**. Whether coordinates are in pixels or normalized units, both boxes must first be transformed into the same reference image:

$$
\mathrm{IoU}(B_{\mathrm{pred}},B_{\mathrm{gt}})=\frac{\lvert B_{\mathrm{pred}}\cap B_{\mathrm{gt}}\rvert}{\lvert B_{\mathrm{pred}}\cup B_{\mathrm{gt}}\rvert}
$$

The RefCOCO family usually counts single-target localization as correct when IoU exceeds 0.5; the exact evaluation script determines how equality at the boundary is handled. GUI clicks are often evaluated by whether a point lies inside an actionable target rather than by box IoU; see [Chapter 4](04-computer-use.md).

## 2.3 Open-vocabulary detection: beyond a fixed category list

Closed-set-trained detectors such as Faster R-CNN and YOLO usually output predefined categories. This does not mean that every extension of those architectures lacks open-vocabulary support. GLIP unifies object detection and phrase grounding as region–text matching, training on detection, grounding, and pseudo-labeled data. OWL-ViT transfers image–text contrastive pretraining to detection by adding prediction heads and fine-tuning for detection. “Open vocabulary” means text queries can be changed, not that any new concept is guaranteed to be recognized. Rare categories, negation, and relational expressions can still fail.

When asked why applying CLIP classification to cropped regions is insufficient, distinguish **whole-image alignment** from **region-level supervision**. Whole-image matching does not directly teach box boundaries, separation of multiple instances, or background suppression. Detection training, region-level examples, and negative examples where the target is absent turn similarity into usable localization.

Open-vocabulary detection can be combined with the coordinate-as-text approach from the previous section: a detector first produces candidate regions, then a language model filters or ranks them or asks follow-up questions. This combines detection accuracy with flexible language reasoning.

## 2.4 Training data: referring expressions and pixel-level annotations

Grounding relies heavily on purpose-built annotations. General image–text pairs, such as scraped web alt text, rarely include precise coordinates:

- **RefCOCO / RefCOCO+ / RefCOCOg**: referring expressions built around COCO objects. RefCOCO+ restricts location descriptions during collection; RefCOCOg descriptions are usually longer, and collection procedures and splits also differ. Results must identify the dataset and split.
- **Visual Genome**: provides dense region descriptions and annotations for objects, attributes, and relationships. Not every visible region is exhaustively labeled, so unlabeled objects must not automatically be treated as absent.
- **Pixel-level annotations**: segmentation-based grounding requires mask annotations, usually at a much higher cost than boxes. Some work lowers this cost with a semi-automatic process: generate masks from detection boxes using a segmentation model such as SAM, then verify them manually.

## 2.5 Evaluation: an overall VQA score is not enough

Grounding requires separate evaluation because it often does not track ordinary VQA scores. A model may know what is in an image without accurately saying where it is. Common evaluation dimensions include:

| Dimension | Metric | Meaning |
|---|---|---|
| Single-target localization | RefCOCO/+/g Acc@IoU>0.5 | One referring expression corresponds to one target box |
| Multi-object detection and counting | mAP; report counting accuracy or absolute error separately | mAP measures box and class matches, not directly whether the count is correct |
| Fine-grained or small-object localization | Resolution-sensitive localization accuracy | Differences under high-resolution tiling or dynamic-resolution strategies |
| Hallucinated localization | Correct rejection when the target is absent | Prevents the model from inventing a box for a nonexistent target |

Hallucinated localization is particularly easy to overlook. An evaluation set containing only present targets cannot distinguish genuine localization accuracy from a tendency to return a box for any prompt.

## 2.6 Common mistakes

### 2.6.1 Equating VQA ability with grounding ability

Correctly answering “图里有几只猫” (“How many cats are in the image?”) does not imply that the model can accurately box each cat. These tasks require different representation granularities and must be evaluated separately, as discussed in Section 2.5.

### 2.6.2 Comparing tasks with one fixed IoU threshold

IoU above 0.5 is a common convention for RefCOCO-style benchmarks, not a universal standard. Small objects, dense scenes, and tasks requiring pixel-level precision, such as medical imaging or clicking GUI elements, need their own tolerance criteria rather than conclusions based on the same threshold.

### 2.6.3 Ignoring coordinate-system and resolution-normalization differences

Models may use normalized coordinates, quantized location tokens, or absolute pixels, with different endpoint conventions. If preprocessing includes resizing, padding, rotation, or tiling, record the inverse transform so predictions can be mapped back to the original image. Multiplying only by the original width and height misaligns outputs when padding or local crops are involved. High resolution preserves small text and objects but increases token and inference costs. Compare accuracy on the same task under different input budgets rather than reporting only maximum-resolution results.

## 2.7 Chapter summary

1. Captioning, VQA, referring expressions, detection, and segmentation demand different outputs; a score on one does not establish the others.
2. Coordinates can come from autoregressive serialization or language-conditioned detection heads. Numeric text, location tokens, and coordinate order must be decoded according to each model's protocol.
3. Open-vocabulary detection, including GLIP and OWL-ViT, uses image–text alignment to move beyond fixed category lists.
4. Grounding requires region-level supervision from manual annotations or verified pseudo-labels; whole-image similarity alone does not provide precise boundaries.
5. Evaluation must be independent of overall VQA scores and include rejection of hallucinated localization when targets are absent.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-02) for this chapter’s sources, reading suggestions, and source notes.
