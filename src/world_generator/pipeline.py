from __future__ import annotations

import shutil
from pathlib import Path

from .export.webxr import export_panorama_viewer, export_splat_viewer
from .media import copy_media, write_json
from .models import (
    Artifact,
    GenerationManifest,
    PipelineStage,
    PipelineStatus,
    StageStatus,
    WorldSpec,
    utc_now,
)
from .prompting import build_world_ir, compile_prompts
from .providers.base import ImageProvider, VideoProvider
from .reconstruction.nerfstudio import NerfstudioReconstructor


class WorldGenerationPipeline:
    def __init__(
        self,
        *,
        image_provider: ImageProvider | None,
        video_provider: VideoProvider | None,
        reconstructor: NerfstudioReconstructor | None,
        ffmpeg_bin: str = "ffmpeg",
    ) -> None:
        self.image_provider = image_provider
        self.video_provider = video_provider
        self.reconstructor = reconstructor
        self.ffmpeg_bin = ffmpeg_bin

    @staticmethod
    def _stage(manifest: GenerationManifest, name: str) -> PipelineStage:
        stage = PipelineStage(name=name, status=StageStatus.RUNNING, started_at=utc_now())
        manifest.stages.append(stage)
        return stage

    @staticmethod
    def _finish(stage: PipelineStage, status: StageStatus, message: str | None = None) -> None:
        stage.status = status
        stage.message = message
        stage.finished_at = utc_now()

    @staticmethod
    def _save(manifest: GenerationManifest, root: Path) -> None:
        manifest.touch()
        write_json(root / "manifest.json", manifest.model_dump(mode="json"))

    def run(
        self,
        spec: WorldSpec,
        output_dir: Path,
        *,
        anchor_image: Path | None = None,
        panorama_image: Path | None = None,
        dry_run: bool = False,
        panorama_only: bool = False,
    ) -> GenerationManifest:
        root = output_dir.resolve()
        prompts_dir = root / "prompts"
        media_dir = root / "media"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)

        manifest = GenerationManifest(spec=spec, status=PipelineStatus.RUNNING)
        planning = self._stage(manifest, "plan-world")
        world_ir = build_world_ir(spec)
        prompts = compile_prompts(spec, has_first_frame=True)
        write_json(root / "world-ir.json", world_ir.model_dump(mode="json"))
        prompt_files = {
            "anchor_image": prompts_dir / "anchor-image.txt",
            "panorama_image": prompts_dir / "panorama-image.txt",
            "h3_video": prompts_dir / "h3-video.txt",
        }
        for key, path in prompt_files.items():
            path.write_text(getattr(prompts, key) + "\n", encoding="utf-8")
            manifest.prompts[key] = str(path.relative_to(root))
        self._finish(planning, StageStatus.SUCCEEDED)
        self._save(manifest, root)

        if dry_run:
            manifest.status = PipelineStatus.PLANNED
            manifest.stages.append(
                PipelineStage(
                    name="external-generation",
                    status=StageStatus.SKIPPED,
                    started_at=utc_now(),
                    finished_at=utc_now(),
                    message="Dry run: no provider or reconstruction command was executed.",
                )
            )
            self._save(manifest, root)
            return manifest

        try:
            anchor_destination: Path | None = None
            anchor_stage = self._stage(manifest, "generate-anchor-image")
            if panorama_only:
                self._finish(
                    anchor_stage,
                    StageStatus.SKIPPED,
                    "Panorama-only mode does not require an H3 anchor image.",
                )
            else:
                anchor_destination = media_dir / "anchor.png"
                if anchor_image is not None:
                    suffix = anchor_image.suffix.lower() or ".png"
                    anchor_destination = media_dir / f"anchor{suffix}"
                    copy_media(anchor_image, anchor_destination)
                    anchor_provider = "user"
                    anchor_metadata: dict[str, object] = {}
                else:
                    if self.image_provider is None:
                        raise RuntimeError("An image provider is required when --anchor-image is absent.")
                    result = self.image_provider.generate(
                        prompts.anchor_image,
                        anchor_destination,
                        size=spec.anchor_size,
                        quality=spec.image_quality,
                    )
                    anchor_provider = result.provider
                    anchor_metadata = result.metadata
                manifest.artifacts["anchor_image"] = Artifact(
                    path=str(anchor_destination.relative_to(root)),
                    kind="image",
                    provider=anchor_provider,
                    metadata=anchor_metadata,
                )
                self._finish(anchor_stage, StageStatus.SUCCEEDED)
            self._save(manifest, root)

            panorama_destination: Path | None = None
            panorama_stage = self._stage(manifest, "generate-panorama-fallback")
            if panorama_image is not None:
                suffix = panorama_image.suffix.lower() or ".png"
                panorama_destination = media_dir / f"panorama{suffix}"
                copy_media(panorama_image, panorama_destination)
                panorama_provider = "user"
                panorama_metadata: dict[str, object] = {}
            elif spec.generate_panorama:
                if self.image_provider is None:
                    raise RuntimeError("An image provider is required to generate the panorama fallback.")
                panorama_destination = media_dir / "panorama.png"
                result = self.image_provider.generate(
                    prompts.panorama_image,
                    panorama_destination,
                    size=spec.panorama_size,
                    quality=spec.image_quality,
                )
                panorama_provider = result.provider
                panorama_metadata = result.metadata
            else:
                panorama_provider = None
                panorama_metadata = {}

            if panorama_destination is not None:
                viewer = export_panorama_viewer(
                    panorama_destination,
                    root / "viewer-panorama",
                    title=spec.name,
                )
                manifest.artifacts["panorama_image"] = Artifact(
                    path=str(panorama_destination.relative_to(root)),
                    kind="equirectangular-image",
                    provider=panorama_provider,
                    metadata=panorama_metadata,
                )
                manifest.artifacts["panorama_viewer"] = Artifact(
                    path=str(viewer.relative_to(root)),
                    kind="webxr-viewer",
                )
                self._finish(panorama_stage, StageStatus.SUCCEEDED)
            else:
                self._finish(panorama_stage, StageStatus.SKIPPED, "Panorama generation disabled.")
            self._save(manifest, root)

            if panorama_only:
                manifest.status = PipelineStatus.SUCCEEDED
                self._save(manifest, root)
                return manifest

            video_stage = self._stage(manifest, "generate-h3-video")
            if self.video_provider is None:
                raise RuntimeError("A video provider is required for H3 generation.")
            if anchor_destination is None:
                raise RuntimeError("H3 image-to-video requires an anchor image.")
            video_destination = media_dir / "h3-video.mp4"
            video_result = self.video_provider.generate(
                prompts.h3_video,
                video_destination,
                duration=spec.duration_seconds,
                resolution=spec.resolution.value,
                ratio=spec.ratio.value,
                first_frame=anchor_destination,
                use_context_ir=spec.use_context_ir,
            )
            video_metadata = dict(video_result.metadata)
            effective_prompt = video_metadata.pop("effective_prompt", None)
            if isinstance(effective_prompt, str) and effective_prompt != prompts.h3_video:
                effective_path = prompts_dir / "h3-effective.txt"
                effective_path.write_text(effective_prompt + "\n", encoding="utf-8")
                manifest.prompts["h3_effective"] = str(effective_path.relative_to(root))
            manifest.artifacts["h3_video"] = Artifact(
                path=str(video_destination.relative_to(root)),
                kind="video",
                provider=video_result.provider,
                metadata=video_metadata,
            )
            self._finish(video_stage, StageStatus.SUCCEEDED)
            self._save(manifest, root)

            reconstruction_stage = self._stage(manifest, "reconstruct-gaussian-splat")
            if self.reconstructor is None:
                self._finish(
                    reconstruction_stage,
                    StageStatus.SKIPPED,
                    "No reconstruction backend configured.",
                )
                manifest.status = PipelineStatus.PARTIAL
            else:
                try:
                    reconstruction = self.reconstructor.reconstruct(
                        video_destination,
                        root / "reconstruction",
                        max_iterations=spec.max_training_iterations,
                    )
                    viewer = export_splat_viewer(
                        reconstruction.splat_path,
                        root / "viewer-splat",
                        title=spec.name,
                    )
                    manifest.artifacts["gaussian_splat"] = Artifact(
                        path=str(reconstruction.splat_path.relative_to(root)),
                        kind="gaussian-splat-ply",
                        provider="nerfstudio-splatfacto",
                        metadata={"config": str(reconstruction.config_path)},
                    )
                    manifest.artifacts["splat_viewer"] = Artifact(
                        path=str(viewer.relative_to(root)),
                        kind="webxr-viewer",
                    )
                    self._finish(reconstruction_stage, StageStatus.SUCCEEDED)
                    manifest.status = PipelineStatus.SUCCEEDED
                except Exception as exc:
                    self._finish(reconstruction_stage, StageStatus.FAILED, str(exc))
                    manifest.errors.append(f"Gaussian Splat reconstruction failed: {exc}")
                    if spec.strict_reconstruction:
                        raise
                    manifest.status = (
                        PipelineStatus.PARTIAL
                        if "panorama_viewer" in manifest.artifacts
                        else PipelineStatus.FAILED
                    )
            self._save(manifest, root)
            return manifest
        except Exception as exc:
            manifest.status = PipelineStatus.FAILED
            manifest.errors.append(str(exc))
            for stage in reversed(manifest.stages):
                if stage.status == StageStatus.RUNNING:
                    self._finish(stage, StageStatus.FAILED, str(exc))
                    break
            self._save(manifest, root)
            raise

    def reconstruct_existing(
        self,
        video: Path,
        output_dir: Path,
        *,
        max_iterations: int | None = None,
    ) -> Path:
        if self.reconstructor is None:
            raise RuntimeError("A reconstruction backend is required.")
        root = output_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        local_video = root / "media" / video.name
        local_video.parent.mkdir(parents=True, exist_ok=True)
        if video.resolve() != local_video.resolve():
            shutil.copy2(video, local_video)
        reconstruction = self.reconstructor.reconstruct(
            local_video,
            root / "reconstruction",
            max_iterations=max_iterations,
        )
        export_splat_viewer(reconstruction.splat_path, root / "viewer-splat", title=video.stem)
        return reconstruction.splat_path
