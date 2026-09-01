# Architecture

## 1. Why this is a pipeline instead of a single call

A generated 2D image provides appearance but no observable parallax. An H3 clip provides temporal
views, but not guaranteed camera intrinsics, camera extrinsics, depth, or a globally consistent
scene representation. A VR renderer needs a spatial representation. World Generator therefore
separates semantic world design, audiovisual generation, geometric reconstruction, and runtime
rendering.

```text
WorldSpec
  └─ WorldIR
      ├─ anchor prompt ────────> image provider ──> canonical first frame
      ├─ panorama prompt ──────> image provider ──> equirectangular fallback
      └─ H3 prompt + first frame ────────────────> camera-motion video
                                                   │
                                                   v
                                        COLMAP camera solving
                                                   │
                                                   v
                                      Nerfstudio Splatfacto
                                                   │
                                                   v
                                         Gaussian Splat PLY
                                                   │
                                 ┌─────────────────┴─────────────────┐
                                 v                                   v
                        Spark / Three.js / WebXR          Panorama / Three.js / WebXR
```

## 2. WorldIR

`WorldIR` is deterministic and versioned. It makes hidden assumptions inspectable before API
charges or training begin. The current schema stores:

- immutable geometry rules;
- navigable floor constraints;
- one explicit camera trajectory;
- exposure, lens, focus, motion, and dynamic-object restrictions;
- reconstruction targets.

A later learned planner can replace the deterministic compiler without changing provider or
reconstruction interfaces.

## 3. H3 capture prompt

The H3 prompt follows the model's structured audiovisual prompt convention:

- `integrated_multimodal_description`
- `overall_soundscape`
- `non_diegetic_music`

For I2VA, the canonical image is assigned to `first_frame`. The prompt deliberately asks for one
continuous shot and only one camera motion. Large or rapid camera motion increases disocclusion and
model invention; tiny motion provides insufficient baseline for reconstruction. The default is a
45-degree slow arc over 10 seconds.

H3-Context-IR is optional. It can improve interpretation of rich multimodal references, but it may
also elaborate a prompt beyond the strict capture instructions. The deterministic reconstruction
prompt is therefore the default.

## 4. Reconstruction

`ns-process-data video` extracts overlapping frames and uses COLMAP to estimate camera poses.
`splatfacto` then optimizes a 3D Gaussian scene. `ns-export gaussian-splat` writes a PLY that the
runtime viewer can load.

Generated footage can violate the static-scene assumption. Typical failure modes are:

- duplicate or disappearing objects;
- non-rigid architecture;
- changing focal length or exposure;
- low texture or repeated ambiguous texture;
- motion blur;
- insufficient camera baseline;
- large newly exposed surfaces invented inconsistently by the video model.

The pipeline records command output under `reconstruction/logs` and keeps the panorama viewer when
3D reconstruction fails.

## 5. Runtime

The splat viewer uses Spark inside the Three.js render loop. WebXR is enabled through Three.js's
`VRButton`. Desktop pointer-lock and WASD movement are included. VR thumbstick translation is
implemented at the camera-rig level.

Nerfstudio coordinate orientation can vary. The generated viewer accepts query parameters without
rewriting the PLY:

```text
?rotX=-1.5708&rotY=0&rotZ=0&scale=1&x=0&y=0&z=0
```

For production, these values should be estimated from the exported camera poses and stored in a
versioned viewer configuration file.

## 6. Provider boundaries

Image and video providers implement small abstract interfaces. This permits future additions such
as local diffusion image models, a locally served H3 checkpoint, or another video model without
changing the pipeline.

The default adapters are:

- OpenAI Image API (`gpt-image-2`);
- MiniMax Open Platform H3 V2 API.

No model weights are copied into this repository.

## 7. Production hardening

Before exposing this as a multi-user service:

1. move media uploads to private, short-lived object-storage URLs;
2. add job queues and idempotency keys;
3. store task IDs and resume polling after process restarts;
4. verify downloaded content type and maximum size;
5. sandbox Nerfstudio and FFmpeg workers;
6. add per-user spend limits and explicit cost confirmation;
7. add scene-quality scoring before expensive reconstruction;
8. convert PLY to a compressed format such as SPZ for delivery;
9. add collision proxies and a safe locomotion boundary;
10. serve viewers over HTTPS outside localhost because WebXR requires a secure context.
