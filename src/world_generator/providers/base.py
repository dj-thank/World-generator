from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProviderResult(BaseModel):
    path: Path
    provider: str
    model: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImageProvider(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        destination: Path,
        *,
        size: str,
        quality: str,
    ) -> ProviderResult:
        raise NotImplementedError


class VideoProvider(ABC):
    @abstractmethod
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
        raise NotImplementedError
