from __future__ import annotations

import time
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, model_validator

from ..config import Settings
from ..errors import ProviderError
from ..media import download_file, media_source_to_url
from .base import ProviderResult, VideoProvider

H3MediaKind = Literal["image_url", "video_url", "audio_url"]
H3Role = Literal[
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
]


class H3Reference(BaseModel):
    kind: H3MediaKind
    source: str | Path
    role: H3Role

    @model_validator(mode="after")
    def validate_kind_matches_role(self) -> H3Reference:
        expected = {
            "first_frame": "image_url",
            "last_frame": "image_url",
            "reference_image": "image_url",
            "reference_video": "video_url",
            "reference_audio": "audio_url",
        }[self.role]
        if self.kind != expected:
            raise ValueError(f"role={self.role} requires kind={expected}, not {self.kind}")
        return self


def _media_item(reference: H3Reference, *, max_inline_bytes: int) -> dict[str, object]:
    source_url = media_source_to_url(reference.source, max_bytes=max_inline_bytes)
    return {
        "type": reference.kind,
        reference.kind: {"url": source_url},
        "role": reference.role,
    }


def build_h3_content(
    prompt: str,
    *,
    first_frame: str | Path | None = None,
    last_frame: str | Path | None = None,
    references: list[H3Reference] | None = None,
    max_inline_bytes: int = 8_000_000,
) -> list[dict[str, object]]:
    if not prompt.strip():
        raise ValueError("H3 prompt cannot be empty.")
    references = references or []
    if any(item.role in {"first_frame", "last_frame"} for item in references):
        raise ValueError("Pass first_frame and last_frame through their dedicated arguments.")
    if (first_frame is not None or last_frame is not None) and references:
        raise ValueError("H3 first/last-frame mode cannot be mixed with reference mode.")
    counts = {
        "reference_image": sum(item.role == "reference_image" for item in references),
        "reference_video": sum(item.role == "reference_video" for item in references),
        "reference_audio": sum(item.role == "reference_audio" for item in references),
    }
    if counts["reference_image"] > 9 or counts["reference_video"] > 3 or counts["reference_audio"] > 3:
        raise ValueError(f"H3 reference count limit exceeded: {counts}")
    if len(references) > 12:
        raise ValueError("H3 accepts at most 12 reference media items in total.")

    content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    if first_frame is not None:
        content.append(
            _media_item(
                H3Reference(kind="image_url", source=first_frame, role="first_frame"),
                max_inline_bytes=max_inline_bytes,
            )
        )
    if last_frame is not None:
        content.append(
            _media_item(
                H3Reference(kind="image_url", source=last_frame, role="last_frame"),
                max_inline_bytes=max_inline_bytes,
            )
        )
    content.extend(
        _media_item(item, max_inline_bytes=max_inline_bytes) for item in references
    )
    return content


def build_generation_payload(
    *,
    model: str,
    prompt: str,
    duration: int,
    resolution: str,
    ratio: str,
    first_frame: str | Path | None = None,
    last_frame: str | Path | None = None,
    references: list[H3Reference] | None = None,
    max_inline_bytes: int = 8_000_000,
) -> dict[str, object]:
    content = build_h3_content(
        prompt,
        first_frame=first_frame,
        last_frame=last_frame,
        references=references,
        max_inline_bytes=max_inline_bytes,
    )
    has_keyframe = first_frame is not None or last_frame is not None
    effective_ratio = "adaptive" if has_keyframe else ratio
    if not has_keyframe and not references and effective_ratio == "adaptive":
        raise ValueError("H3 text-to-video requires a concrete aspect ratio.")
    return {
        "model": model,
        "content": content,
        "resolution": resolution,
        "duration": duration,
        "ratio": effective_ratio,
    }


class MiniMaxH3Client(VideoProvider):
    """MiniMax H3 V2 asynchronous API client."""

    SUCCESS_STATES = {"succeeded", "success"}
    TERMINAL_FAILURES = {"failed", "cancelled", "canceled"}

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.settings.minimax_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.settings.minimax_key()}",
                    "Content-Type": "application/json",
                },
                timeout=self.settings.minimax_request_timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> MiniMaxH3Client:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _post_task(self, endpoint: str, payload: dict[str, object]) -> str:
        last_error: Exception | None = None
        transient_statuses = {429, 500, 502, 503, 504}
        for attempt in range(self.settings.minimax_http_retries + 1):
            try:
                response = self._http().post(endpoint, json=payload)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self.settings.minimax_http_retries:
                    time.sleep(min(2**attempt, 8))
                    continue
                break

            if response.status_code in transient_statuses and attempt < self.settings.minimax_http_retries:
                last_error = ProviderError(self._response_error(response))
                time.sleep(min(2**attempt, 8))
                continue
            if response.is_error:
                raise ProviderError(self._response_error(response))
            try:
                body = response.json()
            except ValueError as exc:
                raise ProviderError("MiniMax returned a non-JSON task response.") from exc
            task_id = body.get("task_id")
            if not task_id:
                raise ProviderError(f"MiniMax did not return task_id: {body}")
            return str(task_id)
        raise ProviderError(f"MiniMax task creation failed: {last_error}") from last_error

    @staticmethod
    def _response_error(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = response.text[:1000]
        return f"MiniMax HTTP {response.status_code}: {body}"

    def _wait_for_task(self, task_id: str) -> dict[str, object]:
        deadline = time.monotonic() + self.settings.minimax_task_timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = self._http().get(f"/v2/query/video_generation/{task_id}")
            except httpx.HTTPError:
                time.sleep(self.settings.minimax_poll_interval_seconds)
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                time.sleep(self.settings.minimax_poll_interval_seconds)
                continue
            if response.is_error:
                raise ProviderError(self._response_error(response))
            try:
                body = response.json()
            except ValueError as exc:
                raise ProviderError("MiniMax task query returned non-JSON data.") from exc

            task = body.get("task")
            if not isinstance(task, dict):
                raise ProviderError(f"MiniMax query returned an unexpected response: {body}")
            status = str(task.get("status", "")).lower()
            if status in self.SUCCESS_STATES:
                return task
            if status in self.TERMINAL_FAILURES:
                raise ProviderError(f"MiniMax task {task_id} ended with status={status}: {task}")
            time.sleep(self.settings.minimax_poll_interval_seconds)
        raise ProviderError(
            f"MiniMax task {task_id} exceeded {self.settings.minimax_task_timeout_seconds:.0f}s timeout."
        )

    def _context_ir_prompt(
        self,
        *,
        content: list[dict[str, object]],
        duration: int,
        ratio: str,
    ) -> tuple[str, str]:
        task_id = self._post_task(
            "/v2/h3_context_ir",
            {
                "model": self.settings.minimax_model,
                "content": content,
                "duration": duration,
                "ratio": ratio,
            },
        )
        task = self._wait_for_task(task_id)
        task_content = task.get("content")
        if not isinstance(task_content, dict) or not task_content.get("prompt"):
            raise ProviderError(f"H3-Context-IR task returned no prompt: {task}")
        return str(task_content["prompt"]), task_id

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
        base_payload = build_generation_payload(
            model=self.settings.minimax_model,
            prompt=prompt,
            duration=duration,
            resolution=resolution,
            ratio=ratio,
            first_frame=first_frame,
            max_inline_bytes=self.settings.minimax_max_inline_media_bytes,
        )
        context_task_id: str | None = None
        effective_prompt = prompt
        if use_context_ir:
            enhanced, context_task_id = self._context_ir_prompt(
                content=base_payload["content"],  # type: ignore[arg-type]
                duration=duration,
                ratio=str(base_payload["ratio"]),
            )
            effective_prompt = enhanced
            content = list(base_payload["content"])  # type: ignore[arg-type]
            content[0] = {"type": "text", "text": enhanced}
            base_payload["content"] = content

        task_id = self._post_task("/v2/video_generation", base_payload)
        task = self._wait_for_task(task_id)
        task_content = task.get("content")
        if not isinstance(task_content, dict) or not task_content.get("url"):
            raise ProviderError(f"H3 generation task returned no output URL: {task}")
        download_file(str(task_content["url"]), destination)
        return ProviderResult(
            path=destination,
            provider="minimax",
            model=self.settings.minimax_model,
            metadata={
                "task_id": task_id,
                "context_ir_task_id": context_task_id,
                "status": task.get("status"),
                "duration": task.get("duration", duration),
                "resolution": task.get("resolution", resolution),
                "ratio": task.get("ratio", base_payload["ratio"]),
                "usage": task.get("usage", {}),
                "effective_prompt": effective_prompt,
            },
        )
