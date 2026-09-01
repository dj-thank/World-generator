from __future__ import annotations

import json
from pathlib import Path

import httpx

from world_generator.config import Settings
from world_generator.providers import minimax_h3
from world_generator.providers.minimax_h3 import MiniMaxH3Client


def test_h3_client_uses_v2_task_flow(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/v2/video_generation":
            return httpx.Response(200, json={"task_id": "video-1"})
        if request.url.path == "/v2/query/video_generation/video-1":
            return httpx.Response(
                200,
                json={
                    "task": {
                        "id": "video-1",
                        "status": "succeeded",
                        "content": {"url": "https://example.invalid/video.mp4"},
                        "duration": 8,
                        "resolution": "768P",
                        "ratio": "16:9",
                    }
                },
            )
        return httpx.Response(404, json={"error": "unexpected path"})

    def fake_download(url: str, destination: Path, **_: object) -> Path:
        assert url == "https://example.invalid/video.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"video")
        return destination

    monkeypatch.setattr(minimax_h3, "download_file", fake_download)
    settings = Settings(
        _env_file=None,
        minimax_api_key="test-key",
        minimax_poll_interval_seconds=0,
        minimax_http_retries=0,
    )
    http = httpx.Client(
        base_url="https://api.minimax.io",
        transport=httpx.MockTransport(handler),
    )
    provider = MiniMaxH3Client(settings, client=http)
    output = tmp_path / "video.mp4"
    result = provider.generate(
        "integrated_multimodal_description: [Shot 1] static scene",
        output,
        duration=8,
        resolution="768P",
        ratio="16:9",
        first_frame=None,
        use_context_ir=False,
    )
    assert result.path.read_bytes() == b"video"
    assert result.metadata["task_id"] == "video-1"
    assert calls == ["/v2/video_generation", "/v2/query/video_generation/video-1"]
    http.close()


def test_h3_context_ir_replaces_only_text_item(monkeypatch, tmp_path: Path) -> None:
    posted: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(json.loads(request.content))
        if request.url.path == "/v2/h3_context_ir":
            return httpx.Response(200, json={"task_id": "context-1"})
        if request.url.path == "/v2/query/video_generation/context-1":
            return httpx.Response(
                200,
                json={
                    "task": {
                        "status": "succeeded",
                        "content": {"prompt": "enhanced reconstruction prompt"},
                    }
                },
            )
        if request.url.path == "/v2/video_generation":
            return httpx.Response(200, json={"task_id": "video-2"})
        if request.url.path == "/v2/query/video_generation/video-2":
            return httpx.Response(
                200,
                json={
                    "task": {
                        "status": "succeeded",
                        "content": {"url": "https://example.invalid/video.mp4"},
                    }
                },
            )
        return httpx.Response(404)

    def fake_download(_url: str, destination: Path, **_kwargs: object) -> Path:
        destination.write_bytes(b"video")
        return destination

    monkeypatch.setattr(minimax_h3, "download_file", fake_download)
    frame = tmp_path / "anchor.png"
    frame.write_bytes(b"x")
    settings = Settings(
        _env_file=None,
        minimax_api_key="test-key",
        minimax_poll_interval_seconds=0,
        minimax_http_retries=0,
    )
    http = httpx.Client(
        base_url="https://api.minimax.io",
        transport=httpx.MockTransport(handler),
    )
    provider = MiniMaxH3Client(settings, client=http)
    result = provider.generate(
        "original prompt",
        tmp_path / "video.mp4",
        duration=8,
        resolution="768P",
        ratio="16:9",
        first_frame=frame,
        use_context_ir=True,
    )
    first_content = posted[0]["content"]
    second_content = posted[1]["content"]
    assert isinstance(first_content, list)
    assert isinstance(second_content, list)
    assert first_content[0]["text"] == "original prompt"
    assert second_content[0]["text"] == "enhanced reconstruction prompt"
    assert second_content[1]["role"] == "first_frame"
    assert result.metadata["effective_prompt"] == "enhanced reconstruction prompt"
    http.close()
