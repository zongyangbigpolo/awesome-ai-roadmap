---
description: Compare multimodal encoders, projection, and cross-attention, covering visual detail, audio/video timing, frozen training components, deployment cost, evidence-based evaluation, and safety boundaries.
---

# Chapter 23: Multimodal Models

## 23.1 Multimodality is not just putting an image into a prompt

Multimodal models process different signals such as images, audio, video, and text, and may output text, structured results, or other modalities. **Check input and output modalities separately**: answering questions about images does not imply image generation, and speech transcription does not imply natural-speech generation.

This chapter focuses on multimodal understanding approaches that connect perceptual representations to a language model. The difficulty is not just alignment into a shared space. It also includes retaining spatial and temporal detail, handling conflicts between modalities, and distinguishing observation from inference. Not every architecture compresses every modality into one global vector.

| Modality | Common raw representation | Main challenges |
|---|---|---|
| Images | Pixel patches or visual features | Resolution, text/small objects, spatial relations |
| Audio | Waveforms, spectra, or acoustic tokens | Sample rate, speakers, timing, and noise |
| Video | Frame sequence plus audio track | Long temporal sequences, motion, cross-frame consistency, and computation |

## 23.2 Encoders, connectors, and language models

For an autoregressive multimodal model that outputs text, a common architecture can be written as:

$$
z_m=E_m(x_m),\qquad h=C(z_m)
$$

$$
p_\theta(y\mid x_m,x_t)
=\prod_{i=1}^{T}p_\theta(y_i\mid y_1,\ldots,y_{i-1},h,x_t)
$$

Here, $E_m$ is a modality encoder, $C$ is a connection or compression module, and $x_t$ is the text input. The representation `h` participates in generation through concatenation, cross-attention, or another mechanism. The prefix is empty for the first output token. These equations describe conditional text generation, not every image- or audio-generation architecture.

| Connection method | Approach | Tradeoff |
|---|---|---|
| **Projection / concatenation** | Map modality features to the LLM's hidden dimension through a linear layer or MLP, then include them in the input sequence | Relatively direct integration; modality tokens consume context and KV capacity |
| **Cross-attention** | Language-side representations query modality features through cross-attention | Can separate the language sequence from modality features, but adds modules and computation and cannot recover information already lost by the encoder |
| **Resampler / token compression** | Compress many modality tokens into fewer latents first | Reduces cost, potentially losing fine-grained information |

These are not mutually exclusive architectures. **How many tokens to retain** and **how to connect them to the language model** are separate design dimensions and are often combined.

- **CLIP** uses image and text encoders for contrastive learning, bringing matched image–text representations closer and separating mismatched samples. It supports retrieval and zero-shot classification, but is not itself a generative chat model and does not guarantee fine-grained spatial understanding.
- **Flamingo** uses a Perceiver Resampler to obtain a fixed number of visual latents, then connects them to a frozen language model through gated cross-attention. It therefore combines compression and cross-attention.
- **The original LLaVA** uses a vision encoder and linear projection. Later versions may use other projectors; do not describe the entire family as having a single architecture.
- **BLIP-2** connects a frozen vision encoder and a frozen language model during pretraining using a Q-Former with learnable queries. Query compression reduces language-side input, but retained detail depends on training objectives and bottleneck capacity. Downstream fine-tuning need not keep every vision parameter frozen.

## 23.3 Representing three modalities

### 23.3.1 Vision

A Vision Transformer typically splits an image into patches and encodes them as a sequence. High-resolution processing often uses tiling, multiple scales, or dynamic resolution. OCR, chart, and small-object tasks need evaluations of whether these strategies retain detail, not merely a general visual-question-answering score.

If both image dimensions double while patch size stays fixed and there is no additional merging, patch count grows by roughly four times. Actual visual-token count also depends on cropping, resizing, merging, and resampling, so pixel count alone cannot predict every model's cost. Qwen2-VL is one published implementation of dynamic resolution and image/text/video positional encoding, not a universal rule for VLMs.

One incorrectly recognized decimal point can invalidate an entire financial-report analysis. Retain original image coordinates and mappings for cropping and scaling. Where needed, combine a general VLM with specialized OCR or table parsing. Conversely, sending only plain OCR text to the model can lose row, column, and layout relationships.

### 23.3.2 Audio

Speech tasks may start from log-Mel spectrograms, pretrained speech encoders, or discrete codec tokens. Whisper itself is an encoder–decoder model for tasks such as speech transcription and translation. Other systems can reuse its encoder, but Whisper is not synonymous with general audio understanding or speech generation.

| Approach | Information flow | Tradeoff |
|---|---|---|
| **Cascaded voice assistant** | ASR → text LLM → TTS | Intermediate text is easy to audit and components are replaceable, but transcription errors propagate, tone/music/environmental sounds may be lost, and latency accumulates across stages |
| **Direct audio interaction** | Audio representations enter a multimodal model and a supported audio-generation module produces the output | May retain more paralinguistic information and optimize interaction jointly; streaming latency, interruption, speakers, and safety controls still need validation. An “end-to-end” label alone does not establish superiority |

A common ASR metric is word error rate:

$$
\mathrm{WER}=\frac{S+D+I}{N}
$$

`S`, `D`, and `I` are substitutions, deletions, and insertions relative to the reference transcript; `N` is the number of reference words. Many insertions can make WER exceed 100%. Empty references need a separate scoring rule rather than division by zero. For Chinese, character error rate (CER) can be reported; WER requires fixed word segmentation, punctuation, and number-normalization rules. Accurate transcription does not imply accurate speaker diarization or timestamps. Audio understanding also needs coverage of environmental sounds, music, and overlapping speech. Generated speech requires separate evaluation of intelligibility, prosody, latency, and speaker consistency where use of the speaker's voice is legally authorized.

### 23.3.3 Video

Video is not a collection of independent images. A model needs to represent content within frames, motion across frames, and events over long intervals. Uniform frame sampling is cheap but can miss a critical instant; dense sampling captures more but rapidly increases tokens and GPU memory. Report frame rate, sampling strategy, maximum duration, and whether the audio track is used.

Timestamps or temporal positional encodings provide ordering cues. Audio, subtitles, and images also need alignment. Seeing only an intact cup and a broken cup in two frames does not prove who broke it. If the key action was not observed, the model should state that evidence is missing rather than filling the gap with commonsense assumptions presented as facts. Retrieving candidate segments and sampling them more densely can control cost, but a miss in the first stage still limits later conclusions.

## 23.4 Training: alignment is not enough

Training objectives can be grouped as follows, without implying that every model follows these three steps:

1. **Pretraining / contrastive alignment**: align representations using image–text, audio–text, or video–text pairs.
2. **Generative pretraining**: predict text, discrete modality tokens, or cross-modal targets.
3. **Multimodal instruction tuning and preference alignment**: use appropriate data to learn question following, evidence citation, or refusal; adding a modality does not automatically confer these behaviors.

Specify which parameters are updated at each stage. Original LLaVA first freezes the vision encoder and LLM and trains the projection layer for feature alignment. Its instruction stage trains the projection and LLM while keeping the vision encoder frozen. BLIP-2 pretraining instead uses a Q-Former with frozen models at both ends.

Freezing backbones saves training resources and leaves their pretrained parameters unchanged. It can reduce forgetting, but trainable connectors or inserted branches still change the combined system's behavior, so retention of existing capabilities needs evaluation. A connector alone may also be insufficient to overcome domain differences. Unfreezing more parameters increases adaptation capacity while also increasing resource usage, overfitting, and forgetting risks.

Record training-data sources, licenses, languages, sampling methods, and annotation processes. Mismatched image–text pairs, ASR noise, misaligned video timing, and synthetic-data biases can teach incorrect associations. A model that uses only language priors in the question and ignores the image may still score well on a biased dataset.

## 23.5 Inference and deployment

Inference cost includes media downloading and decoding, encoders, LLM prefill, and output decoding. High resolution or long video may make perception the bottleneck, but long answers, internal reasoning, or audio output may also dominate latency. Measure each stage rather than assuming the bottleneck.

- Bind encoder-feature caches to media content hashes, model/encoder versions, and preprocessing parameters, including resolution, sample rate, and cropping strategy; isolate them according to tenant permissions.
- Prefix-KV reuse has stricter requirements: text/modality prefixes, positions, templates, and relevant model configurations must also match. The same image in different contexts does not imply that the complete LLM KV can be reused directly.
- Limit input size, frame count, duration, MIME types, decoding time, and response size to avoid resource exhaustion.
- Isolate media downloading, decoding, and model inference. Remote-URL inputs must also follow the SSRF protections in [Tool Protocol Security](../../tools/02-mcp/15-tool-protocol-security.md).
- Distinguish evidence seen or heard from inferences in the output; do not present uncertain observations as facts.

## 23.6 Evaluation and safety

A single aggregate score cannot establish capability. At minimum, break evaluation down by task and risk:

| Dimension | Examples |
|---|---|
| Perception | OCR, object/event recognition, ASR WER, temporal localization |
| Reasoning | Charts, spatial relations, cross-frame causality, multimodal question answering |
| Robustness | Blur, compression, noise, accents, adversarial stickers, out-of-distribution inputs |
| Reliability | Hallucination rate, calibration, refusals, and evidence citations |
| Safety and fairness | Privacy/faces, sensitive-attribute inference, stereotypes, copyright, and harmful content |

For diagnosis, compare three input conditions: original media, human-verified transcripts or structured perception results, and questions without the media. If a correct transcript resolves the problem, investigate perception first. If failure remains, investigate language reasoning or task specifications. If the question alone scores well, check language priors and data leakage. Human transcription can lose spatial or tonal information, so this comparison is diagnostic, not a fully equivalent substitution.

For numerical questions about charts, record OCR, cell-localization, calculation, and final-answer errors separately. Video-event tasks also require temporal-localization scoring, not merely similarity between text descriptions. Even after an image region or video interval is cited, verify that it actually supports the claim.

Text in images or audio can carry indirect prompt injection. A multimodal agent must treat it as untrusted content, not allow it to override system instructions, approvals, or tool permissions. For faces, voiceprints, medical information, minors, or location data, establish legality, consent, retention periods, and human-review requirements first.

## 23.7 Common mistakes

### 23.7.1 Equating image-input support with reliable visual understanding

An interface accepting media establishes input-format compatibility only. OCR, small objects, spatial relations, long video, and cross-modal evidence still need separate evaluation.

### 23.7.2 Comparing aggregate scores without fixing media-processing parameters

Resolution, frame sampling, audio sampling, compression, and budgets all change results. Use the same original media, specify resource limits, and disclose model-specific preprocessing. If models accept different input dimensions, report both native configurations and comparable-budget results rather than forcing incompatible preprocessing.

### 23.7.3 Treating media content as trusted instructions

Image text, subtitles, and audio can all carry indirect prompt injection. Enforce safety boundaries through permissions, data flows, and tool policies—not prompts alone.

## 23.8 Summary

1. Verify multimodal input and output capabilities separately. The encoder–connector–LLM design is a common understanding approach, not the only architecture.
2. Token compression can be combined with projection/concatenation or cross-attention; these control the information bottleneck and connection method separately.
3. Images, audio, and video each require appropriate treatment of space, time, sampling, and noise.
4. Limit media sizes, isolate decoding, and design cache keys correctly in deployment.
5. Evaluate perception, reasoning, reliability, robustness, and safety separately.

> Deploying multimodal systems requires three answers: how evidence is retained, how sequence costs are controlled, and how perception and action boundaries are validated separately.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-llm-23) for this chapter’s sources, reading suggestions, and source notes.
