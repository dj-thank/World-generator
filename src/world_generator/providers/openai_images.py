from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import ProviderError
from ..media import download_file, ensure_parent
from .base import ImageProvider, ProviderResult


def _get(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


class OpenAIImageProvider(ImageProvider):
    """Thin, optional adapter for the OpenAI Image API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(
        self,
        prompt: str,
        destination: Path,
        *,
        size: str,
        quality: str,
    ) -> ProviderResult:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(
                'The optional OpenAI SDK is missing. Install with: pip install -e ".[openai]"'
            ) from exc

        ensure_parent(destination)
        client = OpenAI(api_key=self.settings.openai_key())
        try:
            response = client.images.generate(
                model=self.settings.openai_image_model,
                prompt=prompt,
                size=size,
                quality=quality,
            )
        except Exception as exc:  # SDK-specific exception types vary by release.
            raise ProviderError(f"OpenAI image generation failed: {exc}") from exc

        data = _get(response, "data") or []
        if not data:
            raise ProviderError("OpenAI image generation returned no image data.")
        item = data[0]
        encoded = _get(item, "b64_json")
        remote_url = _get(item, "url")

        if encoded:
            try:
                destination.write_bytes(base64.b64decode(encoded))
            except (ValueError, OSError) as exc:
                raise ProviderError(f"Could not decode generated image: {exc}") from exc
        elif remote_url:
            download_file(str(remote_url), destination)
        else:
            raise ProviderError("OpenAI image response contained neither b64_json nor url.")

        return ProviderResult(
            path=destination,
            provider="openai",
            model=self.settings.openai_image_model,
            metadata={"size": size, "quality": quality},
        )
