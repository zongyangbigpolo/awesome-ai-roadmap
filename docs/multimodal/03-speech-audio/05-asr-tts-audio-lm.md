---
description: Compare CTC, RNN-T, Whisper, and codec-based speech generation, distinguishing the roles and evaluation of continuous acoustic features, semantic tokens, and acoustic tokens.
---

# Chapter 5: Speech Recognition, Synthesis, and Audio Language Models

> This chapter covers architectures and evaluation for three core speech/audio tasks: automatic speech recognition (ASR), text-to-speech synthesis (TTS), and general audio understanding. Full-duplex interaction and interruption handling in real-time conversations are separate engineering problems; see [Chapter 6](06-realtime-duplex-voice.md).

## 5.1 The spectrum of speech tasks

| Task | Input → output | Main challenges |
|---|---|---|
| ASR (automatic speech recognition) | Speech → text | Accents, noise, overlapping speech, proper nouns |
| TTS (text-to-speech synthesis) | Text → speech | Naturalness, prosody, speaker similarity, controllability |
| Audio understanding | Speech / environmental sound / music → text descriptions or structured results | Non-speech acoustic events, speaker identification, musical structure |
| Audio-language models | Audio + text → text | Cross-modal reasoning, such as “这段录音里谁在生气” (“Who sounds angry in this recording?”) |

These tasks share some acoustic representations, but have not converged on a single discrete-token approach. Audio understanding can connect continuous encoder features to an LLM; audio generation can predict codec tokens or continuous acoustic representations. First determine whether the output is a transcript, an acoustic event, or a waveform, then choose the training objective. Not every audio language model is a TTS model.

## 5.2 The evolution of ASR architectures

Early end-to-end ASR had two main approaches:

- **Connectionist Temporal Classification (CTC)** sums over all monotonic alignment paths that collapse to the target transcript, handling cases with more audio frames than labels. It first merges adjacent repeated symbols, then removes blanks, so consecutive identical characters need a blank between them. Its conditional-independence assumption says that label probabilities at each position factorize given the encoder representations—not that the encoder cannot see context. An external language model can improve decoding.
- **RNN-Transducer (RNN-T)** uses an encoder network to represent audio, a prediction network to represent previously emitted labels, and a joint network to choose whether to emit a label or a blank. The prediction network resembles a language model but need not be pretrained as a standalone LM. Low-latency streaming also depends on the encoder's right context; the RNN-T loss alone does not guarantee streamability.

The original Whisper paper trains an encoder–decoder Transformer on 680,000 hours of multilingual, multitask, weakly supervised audio. Task tokens unify transcription, translation into English, language identification, timestamps, and related tasks. That figure belongs to original Whisper and should not be extrapolated to later versions. The model demonstrates robust zero-shot transfer without downstream fine-tuning, but does not prove that weak supervision beats strong supervision for every language and noise condition. The original model processes audio segments rather than providing natively causal streaming ASR. Sliding-window deployment introduces repetition, revisions, and extra computation. Silence and non-speech segments can also produce hallucinated transcripts and need separate testing.

Streaming recognition, which outputs text as someone speaks, and offline recognition, which waits for a complete utterance, impose different architectural constraints. Streaming ASR must emit incremental results with limited or no right context, creating an inherent accuracy–latency tradeoff. Offline ASR can use the full context for bidirectional modeling to improve accuracy.

## 5.3 The evolution of TTS architectures

One classic TTS pipeline maps text to a Mel spectrogram and then uses a vocoder to generate a waveform. Tacotron 2 combines a spectrogram prediction network with a modified WaveNet. Mel spectrograms are compressed representations, but they are not responsible for every timbre or prosody problem: text–audio alignment, duration prediction, training coverage, speaker conditioning, and vocoder quality all affect the result.

VALL-E formulates TTS as codec-token modeling conditioned on text and reference speech. Its original implementation uses an autoregressive model for the first layer of acoustic codes and a non-autoregressive model for the remaining quantization layers, then decodes the codes into a waveform. It does not generate every codebook token in one fully serial sequence. The paper demonstrates zero-shot synthesis prompted by a 3-second recording of an unseen speaker. This result is bounded by its English corpus and evaluation setup; it does not guarantee reliable cloning for every language, noisy recording, or speaker. Reference speech may also convey environmental noise and emotion. Similar timbre does not mean the content was spoken correctly.

## 5.4 Audio tokenization: a shared representation for perception and generation

Neural audio codecs provide representations suited to waveform reconstruction and discrete generation, but audio understanding does not require discretization first. SoundStream and EnCodec use an encoder, residual vector quantization (RVQ), and a decoder. Multiple codebooks progressively encode residuals. Reconstruction quality depends on bitrate, data type, and model; this is not lossless compression.

$$
z=E(x),\qquad \hat z=\sum_{l=1}^{L}q_l(r_{l-1}),\quad r_0=z,\ r_l=r_{l-1}-q_l(r_{l-1})
$$

Here, $q_l$ returns the quantized vector from codebook $l$; the transmitted or predicted value is its discrete index. More quantization layers usually reduce reconstruction error but increase bitrate and generation work. If there are $f$ acoustic frames per second, each frame uses $L$ codebooks of size $K$, and $K$ is a power of 2, the nominal bitrate, ignoring entropy coding and framing, is:

$$
R=fL\log_2 K
$$

`R` is in bit/s: `f` is in frames/second, and each codebook index occupies `log₂K` bits. This is a bitstream rate, not a sampling rate, and it is not the number of language-model generation steps when multiple codebooks are predicted jointly.

This explains why flattening all codebooks into one sequence can be expensive. A model can use time–codebook hierarchies or delayed patterns instead of fully serial generation. Also distinguish **semantic tokens**, which emphasize content and long-term structure, from **acoustic tokens**, which emphasize timbre, prosody, and waveform detail. They are not interchangeable. Qwen-Audio takes continuous audio-encoder features as input, not EnCodec/RVQ codes.

## 5.5 General audio understanding and audio-language models

AudioLM hierarchically models semantic tokens from a self-supervised audio model and acoustic codec tokens, generating audio continuations without text-transcription supervision. Qwen-Audio takes a different audio-to-text approach, connecting an audio encoder to an LLM. SALMONN combines Whisper and BEATs encoders and connects them to a language model through a window-level Q-Former to support both speech and general acoustic events. These systems are not simply “AudioLM with question answering added,” and their connectors cannot all be described as MLP projections.

Evaluation must distinguish recognizing what was said—ASR—from understanding what was heard, including paralinguistic information, events, and musical structure. These require different architectures and training data.

## 5.6 Evaluation

| Task | Metric | Considerations |
|---|---|---|
| ASR | WER (word error rate) / CER (character error rate) | Fix text normalization, tokenization, and corpus conditions; Chinese usually also reports CER |
| TTS naturalness | MOS (mean opinion score) and variants | Human ratings are subjective; report the number of raters and the protocol |
| TTS similarity | Speaker similarity | Measures whether zero-shot voice cloning is faithful to the reference audio |
| Audio understanding | Task-specific accuracy/F1 | Acoustic-event classification, emotion recognition, and other tasks have separate benchmarks; ASR metrics cannot substitute for them |

Very low WER does not guarantee a good voice-assistant experience. Latency, natural prosody, and interruption handling matter too and should be assessed alongside the real-time interaction evaluation in [Chapter 6](06-realtime-duplex-voice.md).

WER is `(substitutions + deletions + insertions) / reference word count`. It can exceed 100% with many insertions and is not “1 minus accuracy.” TTS should also report intelligibility or the error rate when synthesized speech is transcribed back into text. Speaker-embedding similarity alone misses omissions, repetitions, and incorrect numbers. MOS reports need the rating scale, listener population, and confidence intervals; results from different protocols are not directly comparable.

## 5.7 Common mistakes

### 5.7.1 Evaluating a streaming product with offline WER

Streaming ASR revises its partial hypotheses as more speech arrives. Final-transcript WER alone does not capture the user's experience of live on-screen text repeatedly changing. Report the stability of intermediate results as well.

### 5.7.2 Ignoring mismatches between training accents/languages and actual use

Low WER for standard accents and common languages does not establish reliability for dialects, mixed accents, or low-resource languages. Validate separately on real recordings from the target population before deployment.

### 5.7.3 Enabling voice cloning by default as though it were risk-free

Zero-shot voice-cloning methods such as VALL-E can be misused for voice forgery and impersonation. Product deployment should include authorization checks, watermarking, or usage restrictions rather than make cloning available for arbitrary reference recordings by default.

## 5.8 Chapter summary

1. CTC, RNN-T, and attention-based encoder–decoders coexist; choose according to alignment assumptions, right context, and latency budgets.
2. Alongside the acoustic-features-plus-vocoder pipeline, neural codec language models such as VALL-E turn speech generation into language modeling over discrete tokens.
3. RVQ codecs suit discrete acoustic generation. Continuous encoder features, semantic tokens, and acoustic tokens serve distinct roles and must not be conflated.
4. Audio-language models such as Qwen-Audio and SALMONN must understand paralinguistic information as well as recognize words, so they need evaluation beyond ASR.
5. TTS voice cloning should be paired with authorization and abuse prevention, not unrestricted default access.

> When choosing an audio representation, first ask whether it must preserve linguistic content, acoustic detail, or both. That determines the compression method and the errors that need separate evaluation.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-05) for this chapter’s sources, reading suggestions, and source notes.
