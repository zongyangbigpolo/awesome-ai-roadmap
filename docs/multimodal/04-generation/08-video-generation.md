---
description: Compare temporal layers and spatiotemporal patches for video generation, explaining sequence costs, long-video drift, conditioning, and the evaluation limits of FVD and VBench.
---

# Chapter 8: Video Generation Models

> This chapter covers the temporal dimension that video adds to image generation. For the generative foundations of diffusion and flow matching, see [Chapter 7](07-diffusion-flow-matching-image.md). We assume that background and focus on video-specific architectural extensions and evaluation.

## 8.1 The extra dimension in video

Applying an image-generation model independently to each video frame produces flicker, drifting object shapes, and discontinuous motion. Independent generation provides no mechanism ensuring that adjacent frames belong to the same continuous physical process. Video models must explicitly represent the **time dimension**, introducing these central problems:

| Problem | Explanation |
|---|---|
| Temporal consistency | Subject identity and scene state should remain coherently continuous; occlusion, fast motion, and shot changes can legitimately cause nonsmooth changes |
| Motion modeling | Generate plausible object trajectories rather than a stack of static appearances |
| Compute and GPU-memory cost | The added time axis makes sequence length and memory use grow substantially with duration and frame rate |
| Long-duration generation | Extrapolating beyond training durations can cause content drift and forgetting of early-frame information |

## 8.2 Architectural approaches: from temporal layers to spatiotemporal modeling

One approach adds temporal attention or temporal convolutions to an image network so frames share information. Video Diffusion Models uses a factorized spatial–temporal architecture and joint image/video training. Imagen Video uses video diffusion with spatial and temporal super-resolution cascades. These demonstrate the feasibility of temporal extensions, but cannot all be reduced to “freeze an existing image model and insert temporal layers.” Stable Video Diffusion explicitly studies stages including image pretraining, video pretraining, and high-quality video fine-tuning.

Another approach divides compressed video representations into spatiotemporal patches and feeds them to a Transformer. OpenAI's **2024 Sora technical report** describes this design and training with variable durations, resolutions, and aspect ratios. It does not fully disclose attention implementations at every layer, so it does not justify claiming that spatial and temporal layers are no longer distinguished, nor should it be extrapolated to every later Sora product. Variable sizes still need positional encodings, bucketing or packing, masks, and memory budgets; patches alone do not make them work automatically. The two approaches can be combined rather than treated as a strict first-generation/second-generation replacement.

## 8.3 Spatiotemporal patches and Transformer scalability

A Transformer backbone can support diffusion or flow matching, but **the 2024 Sora report is not evidence that Sora uses flow matching**. Moving from images to video also involves temporal compression, spatiotemporal positional encodings, frame-rate conditioning, and attention scope—not merely a different patch name:

1. **Scalability**: relevant reports observe quality changes with increased training compute. This does not prove that data volume, parameter count, and video duration can grow indefinitely under the same scaling rule. Video data quality, motion distributions, and compression losses can still become bottlenecks.
2. **Compute cost**: for latent dimensions $T'\times H'\times W'$ and patch dimensions $p_t\times p_h\times p_w$, with exact divisibility, sequence length is:

$$
N=\frac{T'}{p_t}\frac{H'}{p_h}\frac{W'}{p_w}
$$

The attention part of full attention costs $O(N^2d)$, but projections, feed-forward layers, codecs, and sampling steps also incur costs. FlashAttention reduces intermediate-matrix storage without eliminating full attention's quadratic computation. Local, factorized, or sparse attention changes the cost, so video cannot universally be declared a fixed number of orders of magnitude more expensive than images.

## 8.4 Consistency, controllability, and the limits of long-video generation

Control inputs may include text, a first frame, reference images, poses, or camera trajectories; support depends on training data and model interfaces. The Stable Video Diffusion paper studies text-to-video and image-to-video. Its initial image-conditioned weight release should not be confused with the task scope of the entire paper. Common limitations include:

- **Long-video drift**: limited training durations make extrapolation prone to shifting subjects, objects disappearing and reappearing, abrupt scene changes, and other inconsistencies.
- **Approximate physical regularities**: technical reports and public evaluations emphasize that these models learn statistical approximations to the physical world, not explicit physical simulations. Complex collisions, fluids, and multi-object interactions can still violate physical intuition. Evaluations and product descriptions should state this limitation rather than claim a dependable “world simulator.”
- **Cost and latency**: for similar models, equal resolution, and comparable sampling settings, multiple frames usually cost more than one. Specify duration, frame rate, resolution, sampling budget, and queue policy rather than directly comparing different models.

Long videos can use overlapping windows, keyframes or hierarchical generation, and conditioning on past clips. Overlap can soften seams while accumulating errors; compressed history saves memory while losing subject details; stronger reference-image constraints support identity preservation but may suppress motion. These are tradeoffs, not guarantees of temporal consistency. Also distinguish preserving subject identity from keeping pixels unchanged during camera movement—the latter can prevent plausible motion.

## 8.5 Evaluation

| Dimension | Metric | Considerations |
|---|---|---|
| Distribution-level visual/temporal quality | FVD (Fréchet Video Distance) | Compares distribution statistics of video-encoder features; subtle motion or physical errors may go undetected |
| Text consistency | Image–text / text–video alignment scores and human evaluation | Whether generated subjects, actions, and styles follow the text; frame-level scores alone do not establish temporal order |
| Motion and consistency | VBench component metrics plus human evaluation | Separate dynamic degree, motion smoothness, flicker, and subject consistency; physical plausibility still needs dedicated validation |
| Robustness to duration and resolution | Quality-degradation curves reported separately by duration/resolution | Avoid presenting only a few selected examples under optimal conditions |

VBench already provides automated dimensions for subject consistency, motion smoothness, and temporal flicker, so motion evaluation is not limited to human methods. However, a static video may achieve excellent smoothness scores; dynamic degree and the prompt's requirements must also be checked. FVD comparisons should fix sample size, frame count, frame rate, cropping, and feature extractor. Overall scores from different conditions should not be directly ranked.

## 8.6 Common mistakes

### 8.6.1 Equating the ability to generate long videos with stable long-video quality

Extrapolation beyond training durations often brings drift and reduced consistency. Evaluation and publicity should explicitly report quality changes across duration ranges rather than show only selected best clips.

### 8.6.2 Treating demonstration videos as proof of physical simulation

Visual plausibility does not prove verifiable physical simulation. Applications requiring physical correctness should test conservation, contact, post-occlusion state, and action consequences, and report failure rates. Selected demonstrations establish neither failure rates nor the model's internal mechanism.

### 8.6.3 Ignoring compute constraints in product design

Choose synchronous responses or asynchronous jobs according to generation length and measured latency. Longer jobs need progress reporting, cancellation, quotas, failure retries, and artifact-retention policies. Simply changing an image API's return type to video is not enough.

## 8.7 Chapter summary

1. Video adds temporal consistency and motion modeling, and multi-frame computation usually increases resource needs.
2. Temporal layers and spatiotemporal patches are compatible design choices. Variable duration and resolution need support from training, positional representations, and scheduling.
3. With fixed compression and patch settings, sequence length grows multiplicatively with spatial dimensions and duration. Attention structure and sampling budgets also affect cost.
4. Long videos can drift, and learned physical regularities are statistical approximations rather than exact simulation. Product descriptions must make both limits clear.
5. FVD, VBench, and human evaluation complement one another. Check image quality, amount of motion, subject consistency, and degradation under different generation budgets together.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-08) for this chapter’s sources, reading suggestions, and source notes.
