from __future__ import annotations

from pathlib import Path

from world_generator.models import PipelineStatus, StageStatus, WorldSpec
from world_generator.pipeline import WorldGenerationPipeline
from world_generator.providers.base import ImageProvider, ProviderResult


class FakeImageProvider(ImageProvider):
    def generate(
        self,
        prompt: str,
        destination: Path,
        *,
        size: str,
        quality: str,
    ) -> ProviderResult:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-image")
        return ProviderResult(
            path=destination,
            provider="fake",
            model="fake-image",
            metadata={"size": size, "quality": quality, "prompt_length": len(prompt)},
        )


def test_dry_run_writes_ir_prompts_and_manifest(tmp_path: Path) -> None:
    pipeline = WorldGenerationPipeline(
        image_provider=None,
        video_provider=None,
        reconstructor=None,
    )
    manifest = pipeline.run(
        WorldSpec(prompt="A static library with a clear central aisle"),
        tmp_path,
        dry_run=True,
    )
    assert manifest.status == PipelineStatus.PLANNED
    assert (tmp_path / "world-ir.json").is_file()
    assert (tmp_path / "prompts" / "anchor-image.txt").is_file()
    assert (tmp_path / "prompts" / "h3-video.txt").is_file()
    assert (tmp_path / "manifest.json").is_file()


def test_panorama_only_skips_anchor_and_video(tmp_path: Path) -> None:
    pipeline = WorldGenerationPipeline(
        image_provider=FakeImageProvider(),
        video_provider=None,
        reconstructor=None,
    )
    manifest = pipeline.run(
        WorldSpec(prompt="A quiet moss-covered garden"),
        tmp_path,
        panorama_only=True,
    )
    assert manifest.status == PipelineStatus.SUCCEEDED
    assert "anchor_image" not in manifest.artifacts
    assert "panorama_viewer" in manifest.artifacts
    anchor_stage = next(stage for stage in manifest.stages if stage.name == "generate-anchor-image")
    assert anchor_stage.status == StageStatus.SKIPPED
    assert (tmp_path / "viewer-panorama" / "index.html").is_file()
