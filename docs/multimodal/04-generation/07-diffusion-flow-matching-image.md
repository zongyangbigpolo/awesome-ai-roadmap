---
description: Derive noise-prediction and conditional flow-matching objectives, explaining the assumptions behind DDIM, CFG, latent-space compression, and image-generation evaluation.
---

# Chapter 7: Diffusion Models, Flow Matching, and Image Generation

> This chapter focuses on the **generative modeling paradigms** behind image generation—diffusion and flow matching—and their application to text-to-image tasks. For the additional temporal-consistency problems of video generation, see [Chapter 8](08-video-generation.md). Generating data from noise is a different question from connecting multimodal inputs to a language model for understanding, covered in [Chapter 1](../01-foundations/01-multimodal-fusion-architecture.md).

## 7.1 The central problem of generative modeling

Image generation learns a data distribution that can be sampled; text-to-image generation must also learn the distribution $p(x\mid c)$ given a condition $c$. This chapter covers diffusion and flow matching. The former can start from a discrete noising chain; the latter is based on a continuous velocity field. They can also be related under particular continuous-time parameterizations. They are not the only image-generation methods: autoregressive models, GANs, and other approaches exist.

## 7.2 Diffusion models: adding and removing noise

Denoising Diffusion Probabilistic Models (DDPM) define a fixed **forward noising process**. Starting from real data $x_0$, Gaussian noise is gradually added over $T$ steps until $x_T$ is approximately pure noise:

$$
q(x_t\mid x_{t-1})=\mathcal{N}\left(x_t;\sqrt{1-\beta_t}x_{t-1},\ \beta_t I\right)
$$

Here, $\beta_t$ is a noise-schedule coefficient. Defining $\bar\alpha_t=\prod_{s=1}^{t}(1-\beta_s)$ lets us directly sample a noisy example at any time without traversing the entire chain during training:

$$
x_t=\sqrt{\bar\alpha_t}x_0+\sqrt{1-\bar\alpha_t}\epsilon,\qquad
\epsilon\sim\mathcal{N}(0,I)
$$

The simplified noise-prediction loss trains the network to predict the **aggregate noise** $\epsilon$ here, not the independent noise newly added at a particular step:

$$
\mathcal{L}=\mathbb{E}_{x_0,\epsilon,t}\left[\lVert \epsilon-\epsilon_\theta(x_t,t)\rVert^2\right]
$$

At inference time, network predictions and sampler updates progressively transform noise into a sample. The **score** here is the gradient of log probability density with respect to the sample, not an image-quality rating. Under the Gaussian noising process above, noise prediction is proportional to the score of the **noisy marginal distribution**:

$$
s_\theta(x_t,t)=-\frac{\epsilon_\theta(x_t,t)}{\sqrt{1-\bar\alpha_t}}
$$

This does not directly estimate the gradient of the clean-data distribution at every time. Noise prediction, data prediction, and velocity parameterizations can be converted into one another, but time-step weighting and noise schedules change the actual optimization problem. Arbitrary training objectives are not all equivalent.

## 7.3 Latent diffusion: moving diffusion into latent space

Latent diffusion first trains a compressive autoencoder, learns denoising over lower-spatial-resolution latents, and then decodes them into images. The original paper discusses autoencoders with KL regularization and vector quantization, among other options. Stable Diffusion 1/2 uses a KL-regularized autoencoder; not every LDM should be restricted to that same kind of VAE. Text conditioning enters selected cross-attention modules in the denoising network, not literally every layer. Compression reduces spatial computation, but text, fine textures, and exact geometry may already be lost during autoencoding. More sampling steps cannot restore details that the tokenizer cannot represent.

## 7.4 Faster sampling and controllability

Original DDPM sampling follows a multi-step reverse chain, with cost primarily determined by the number of network evaluations. Sampling acceleration and conditional guidance are distinct problems:

- **DDIM sampling** constructs a non-Markovian process sharing DDPM's training objective. Setting its stochasticity parameter to zero gives deterministic sampling; nonzero stochasticity is also possible. A sparser time grid can be used, but reducing steps is a quality–cost tradeoff, not a guarantee of equal quality. Its continuous limit is related to an ODE, but finite-step DDIM should not be described as an exact ODE solution.
- **Classifier-free guidance (CFG)** randomly drops conditioning information, such as text, during training so the model learns both conditional and unconditional generation. At inference time, a weighted extrapolation of the difference between their predictions strengthens adherence to the text condition. Excessive guidance can sacrifice diversity and realism, so the coefficient needs task-specific tuning.

For example, CFG in noise-prediction form is:

$$
\hat\epsilon=\epsilon_\theta(x_t,t,\varnothing)+
w\left[\epsilon_\theta(x_t,t,c)-\epsilon_\theta(x_t,t,\varnothing)\right]
$$

Here, $w=1$ is ordinary conditional prediction. Other sources may define the coefficient with an offset of 1, so values cannot be copied blindly. Standard CFG needs both conditional and unconditional predictions at every step. They may be batched together, but this is not free sampling acceleration. Replacing the unconditional branch with a negative prompt, or using a guidance-distilled model, changes the interpretation again.

## 7.5 What does flow matching learn, and why does training not require solving the full trajectory?

Flow matching trains a velocity field by sampling positions along a path and their corresponding velocities. It does not need to simulate the complete trajectory for every training update; integration along the learned field happens at inference. It can use diffusion probability paths or other paths, without first defining a discrete noising–denoising Markov chain. Its continuous ordinary differential equation is:

$$
\frac{dx_t}{dt}=v_\theta(x_t,t)
$$

Consider a linear conditional path between noise $z$ and data $x$. This section uses $t=0$ for noise and $t=1$ for data, reversing the time direction of the DDPM notation above:

$$
x_t=(1-t)z+tx,\qquad
\mathcal{L}_{\mathrm{CFM}}=
\mathbb{E}_{z,x,t}\left[\lVert v_\theta(x_t,t)-(x-z)\rVert^2\right]
$$

The simplest setup independently samples standard Gaussian noise `z` and training data `x`, with `t` uniform on `[0,1]`. Changing endpoint pairings or time sampling changes the training conditions. Training directly samples $(z,x,t)$ and regresses the conditional velocity, without numerically integrating the entire ODE; a solver performs integration at inference. The key follow-up is that **straight conditional paths between sample pairs do not imply straight trajectories in the learned marginal velocity field**. At the same location, the model learns an average of multiple conditional velocities, while finite capacity and numerical discretization introduce further errors. Linear interpolation therefore does not guarantee one-step or few-step generation. Rectified flow's reflow and distillation are methods for further improving trajectories and sampling efficiency.

The published Stable Diffusion 3 paper combines rectified flow, reweighted time-step sampling, and MMDiT. Text and images have separate weights and exchange information through joint attention. Flow matching is a training objective; a Transformer is a network backbone. They are not inseparable.

Diffusion and flow matching are not mutually exclusive systems. Under particular path assumptions, their objectives can be derived from one another. Practical differences lie more in noise schedules, path design, and engineering choices than in entirely different generative principles.

## 7.6 Architectural positioning of representative systems

| System | Backbone architecture | Key design |
|---|---|---|
| Stable Diffusion (versions 1/2) | U-Net + latent diffusion | Released weights; check the applicable license before use |
| Stable Diffusion 3 | MMDiT + rectified flow | Bidirectional image–text interaction and time-step sampling design |
| DALL·E 3 (2023 technical report) | Latent-space generation; the appendix additionally discloses a diffusion decoder mapping latents back to pixels | Focuses on mixing synthetic and original captions; partial architectural disclosure is not a complete public training implementation |
| Imagen | Cascaded pixel-space diffusion: base resolution plus super-resolution cascades | Uses a language model pretrained on large-scale text-only data as its text encoder |

This table locates publicly described designs, not a product leaderboard as of a particular date. Undisclosed internals should remain unknown. A few representative models also do not establish that every image-generation method uses diffusion or flow matching.

## 7.7 Evaluation: automatic metrics and human assessment are both necessary

| Dimension | Metric | Limitations |
|---|---|---|
| Image quality and diversity | FID (Fréchet Inception Distance) | Compares Gaussian approximations based on Inception feature means and covariances; does not directly measure each image's text adherence |
| Text–image consistency | CLIPScore | Depends on CLIP alignment and may disagree with human judgments of prompt adherence |
| Overall preference | Human pairwise comparisons | Closer to actual user experience, but expensive and affected by the reviewer population |

Improved FID and CLIPScore do not necessarily mean improved human preference. Rankings often disagree, so production model selection should include human evaluation rather than rely on one automatic metric.

For a prompt such as “两个蓝杯子在红盘子左侧” (“two blue cups to the left of a red plate”), separately check count, attribute binding, relative position, and text rendering. Global CLIP similarity can hide local condition errors. When comparing samplers, fix the model, prompt set, random-seed policy, resolution, guidance definition, and number of network evaluations. Report latency and GPU memory too, so unequal compute budgets are not mistaken for methodological superiority.

## 7.8 Common mistakes

### 7.8.1 Assuming more steps are always better

The benefit of sampling steps depends on whether the model was trained or distilled for few-step generation, the solver order, time grid, and guidance strength. More steps may reduce discretization error but cannot eliminate data bias or autoencoder losses. Measure the quality–latency curve on the target model; the labels “DDIM” and “flow matching” alone do not tell you how many steps it needs.

### 7.8.2 Always increasing classifier-free guidance

Increasing guidance may improve text adherence over a certain range, but this is not a monotonic guarantee. Excessive guidance can cause saturation, distortion, and reduced diversity. Tune it for the specific model, parameterization, and prompt type.

### 7.8.3 Ranking models trained at different resolutions or on different datasets by FID alone

FID is sensitive to image resolution, the reference dataset, and the feature-extractor version. Direct cross-paper or cross-setting comparisons are misleading; reproduce comparisons under the same evaluation protocol.

## 7.9 Chapter summary

1. Diffusion and flow matching can both sample data from noise. Their relationship requires explicit path assumptions, parameterizations, and time-step weights.
2. Latent diffusion moves the process into an autoencoder's compressed space, reducing computation while imposing reconstruction-quality limits.
3. DDIM and classifier-free guidance address sampling steps and text consistency respectively, providing core techniques for efficient and controllable generation.
4. Flow matching can train without trajectory simulation. Straight conditional paths do not guarantee straight generation trajectories, and few-step quality still needs validation.
5. Automatic metrics such as FID and CLIPScore have distinct limitations; production model selection should include human preference evaluation.

## References

<!-- centralized-bibliography -->
See the [central bibliography](../../book/references.md#reading-multimodal-07) for this chapter’s sources, reading suggestions, and source notes.
