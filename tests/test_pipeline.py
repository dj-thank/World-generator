from __future__ import annotations

from pathlib import Path

from world_generator.models import PipelineStatus, StageStatus, WorldSpec
from world_generator.pipeline import WorldGenerationPipeline
from world_generator.providers.base import ImageProvider, ProviderResult, VideoProvider


class FakeImageProvider(ImageProvider):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(
        self,
        prompt: str,
        destination: Path,
        *,
        size: str,
        quality: str,
    ) -> ProviderResult:
        self.calls.append(prompt)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-image")
        return ProviderResult(
            path=destination,
            provider="fake",
            model="fake-image",
            metadata={"size": size, "quality": quality, "prompt_length": len(prompt)},
        )


class FakeVideoProvider(VideoProvider):
    def generate(
        self,
        prompt: str,
        destination: Path,
        *,
        duration: int,
        resolution: str,
        ratio: str,
        first_frame: str | Path | None,
        use_context_ir: bool,
    ) -> ProviderResult:
        assert first_frame is not None
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-video")
        return ProviderResult(
            path=destination,
            provider="fake-video",
            model="fake-h3",
            metadata={"effective_prompt": "expanded reconstruction prompt"},
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


def test_provider_pipeline_keeps_fallback_and_effective_prompt_provenance(
    tmp_path: Path,
) -> None:
    images = FakeImageProvider()
    pipeline = WorldGenerationPipeline(
        image_provider=images,
        video_provider=FakeVideoProvider(),
        reconstructor=None,
    )

    manifest = pipeline.run(WorldSpec(prompt="A static gallery"), tmp_path)

    assert manifest.status == PipelineStatus.PARTIAL
    assert len(images.calls) == 2
    assert "anchor_image" in manifest.artifacts
    assert "h3_video" in manifest.artifacts
    assert "panorama_viewer" in manifest.artifacts
    assert manifest.prompts["h3_effective"] == "prompts/h3-effective.txt"
    assert (tmp_path / "prompts" / "h3-effective.txt").read_text(encoding="utf-8") == (
        "expanded reconstruction prompt\n"
    )
