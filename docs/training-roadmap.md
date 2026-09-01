# Training roadmap: from orchestration to a camera-conditioned world model

The MVP uses existing image and video models plus geometric reconstruction. A stronger system should
fine-tune H3 itself as an H3 derivative so that camera motion is explicitly conditioned and scene
geometry stays stable.

## Target behavior

Input:

- text world description;
- optional canonical image or multimodal references;
- camera intrinsics;
- timestamped SE(3) camera trajectory;
- static/dynamic masks;
- target duration and resolution.

Output:

- video that follows the exact trajectory;
- stable static geometry and materials;
- optional depth, normals, confidence, and visibility maps;
- synchronized audio kept separate from geometry supervision.

## Dataset unit

```text
sample-000001/
├── prompt.txt
├── anchor.png
├── video.mp4
├── cameras.json          # intrinsics + world-to-camera transform per frame
├── depth/000000.exr
├── normals/000000.exr
├── static-mask/000000.png
├── visibility/000000.png
└── metadata.json         # capture source, license, scene scale, split
```

Prefer real multi-view captures and renderer-generated scenes with exact camera/depth ground truth.
Do not build a separate model by harvesting H3 outputs where the H3 license prohibits that use. If
H3-generated samples are used, keep the resulting work within the allowed H3/derivative scope and
obtain legal review.

## Conditioning design

1. Encode each camera pose as translation, 6D rotation, focal length, principal point, and timestamp.
2. Project the camera sequence into trajectory tokens.
3. Insert trajectory tokens into the packed multimodal sequence before the video latent tokens.
4. Add trajectory-conditioned AdaLN modulation while retaining H3's modality separation.
5. During classifier-free guidance training, independently drop text, image, and trajectory
   conditions so the model learns controllable combinations.

## Losses

The normal denoising or flow-matching objective remains the primary loss. Add low-weight auxiliary
terms on decoded or predicted clean frames:

- **Pose adherence**: a frozen visual odometry network predicts relative poses that must match the
  requested trajectory.
- **Epipolar consistency**: feature correspondences should respect the fundamental matrix for known
  camera pairs.
- **Depth reprojection**: predicted depth warps adjacent frames; valid static pixels should agree.
- **Feature reprojection**: self-supervised features should remain consistent under pose/depth
  warping when raw photometric loss is too strict.
- **Loop closure**: repeated viewpoints should recover the same appearance and geometry.
- **Static topology**: correspondence tracks penalize object birth, death, duplication, and
  non-rigid deformation in static regions.
- **Exposure stability**: global color and luminance statistics should not drift unless requested.

## Curriculum

### Phase A — deterministic renderer data

Train on simple synthetic rooms and outdoor scenes with exact camera paths. Start with short, narrow
baseline arcs and static lighting.

### Phase B — photorealistic rendered worlds

Increase texture complexity, occlusion, reflective materials, and longer trajectories. Add first
frame and first+last frame conditions.

### Phase C — real captures

Use licensed indoor/outdoor videos with COLMAP-verified poses. Reject clips with low registration
coverage or dynamic objects.

### Phase D — multimodal references

Add H3 Ref2VA-style image/video/audio inputs while keeping camera trajectory as a hard condition.

## Evaluation

Measure more than image quality:

- COLMAP registered-frame ratio;
- absolute and relative pose error;
- reprojection error;
- depth consistency and scale drift;
- long feature-track survival;
- loop-closure appearance error;
- 3DGS reconstruction PSNR/SSIM/LPIPS on held-out poses;
- geometry completeness and floaters;
- human comfort in VR, including acceleration and horizon stability.

A candidate checkpoint should not advance merely because its video benchmark score improves. The
primary gate is whether downstream reconstruction and novel-view rendering improve.

## Direct 3D decoder research path

After camera-conditioned H3 is stable, train an additional decoder from video latents and camera
tokens to a compact 3D Gaussian representation. The decoder can predict Gaussian position,
covariance, opacity, color coefficients, and confidence, followed by differentiable rendering loss
from held-out views. This removes COLMAP from inference, but it should remain a later stage because
metric ambiguity and generated-view inconsistency otherwise become hidden inside the decoder.
