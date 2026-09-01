from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class H3Resolution(StrEnum):
    P768 = "768P"
    P2K = "2K"


class AspectRatio(StrEnum):
    WIDE = "16:9"
    CINEMA = "21:9"
    LANDSCAPE = "4:3"
    SQUARE = "1:1"
    PORTRAIT = "3:4"
    VERTICAL = "9:16"


class CameraPath(StrEnum):
    ARC_CLOCKWISE = "arc-clockwise"
    ARC_COUNTERCLOCKWISE = "arc-counterclockwise"
    TRUCK_RIGHT = "truck-right"
    TRUCK_LEFT = "truck-left"
    PUSH_IN = "push-in"


class PipelineStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


class WorldSpec(BaseModel):
    """Stable, serializable intent for one generated world."""

    name: str = "generated-world"
    prompt: str = Field(min_length=3)
    style: str = "photorealistic cinematic environment"
    duration_seconds: int = Field(default=10, ge=4, le=15)
    resolution: H3Resolution = H3Resolution.P768
    ratio: AspectRatio = AspectRatio.WIDE
    camera_path: CameraPath = CameraPath.ARC_CLOCKWISE
    orbit_degrees: int = Field(default=45, ge=10, le=90)
    camera_height_m: float = Field(default=1.65, ge=0.5, le=3.0)
    generate_panorama: bool = True
    panorama_size: str = "2048x1024"
    anchor_size: str = "1536x864"
    image_quality: str = "medium"
    use_context_ir: bool = False
    strict_reconstruction: bool = False
    max_training_iterations: int | None = Field(default=None, ge=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = "-".join(value.strip().lower().replace("_", "-").split())
        return normalized or "generated-world"


class CameraPlan(BaseModel):
    movement: CameraPath
    approximate_degrees: int
    duration_seconds: int
    height_m: float
    fixed_focal_length: bool = True
    fixed_exposure: bool = True
    continuous_shot: bool = True


class WorldIR(BaseModel):
    """Intermediate representation shared by prompt generation and reconstruction."""

    version: str = "world-ir/0.1"
    world_name: str
    scene_intent: str
    visual_style: str
    immutable_geometry: list[str]
    navigable_regions: list[str]
    camera: CameraPlan
    generation_constraints: list[str]
    reconstruction_targets: list[str]


class PipelineStage(BaseModel):
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None


class Artifact(BaseModel):
    path: str
    kind: str
    provider: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationManifest(BaseModel):
    version: str = "world-generator/0.1"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: PipelineStatus = PipelineStatus.PLANNED
    spec: WorldSpec
    stages: list[PipelineStage] = Field(default_factory=list)
    artifacts: dict[str, Artifact] = Field(default_factory=dict)
    prompts: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = utc_now()
