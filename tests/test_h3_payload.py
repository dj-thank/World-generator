from pathlib import Path

import pytest
from pydantic import ValidationError

from world_generator.providers.minimax_h3 import (
    H3Reference,
    build_generation_payload,
    build_h3_content,
)


def test_first_frame_uses_official_nested_url_shape(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"not-a-real-png-but-valid-for-payload-test")
    payload = build_generation_payload(
        model="MiniMax-H3",
        prompt="one continuous shot",
        duration=8,
        resolution="768P",
        ratio="16:9",
        first_frame=image,
    )
    assert payload["ratio"] == "adaptive"
    content = payload["content"]
    assert isinstance(content, list)
    item = content[1]
    assert item["type"] == "image_url"
    assert item["role"] == "first_frame"
    image_url = item["image_url"]
    assert isinstance(image_url, dict)
    assert image_url["url"].startswith("data:image/png;base64,")


def test_text_to_video_keeps_concrete_ratio() -> None:
    payload = build_generation_payload(
        model="MiniMax-H3",
        prompt="one continuous shot",
        duration=8,
        resolution="2K",
        ratio="21:9",
    )
    assert payload["ratio"] == "21:9"


def test_text_to_video_rejects_adaptive_ratio() -> None:
    with pytest.raises(ValueError, match="concrete aspect ratio"):
        build_generation_payload(
            model="MiniMax-H3",
            prompt="one continuous shot",
            duration=8,
            resolution="768P",
            ratio="adaptive",
        )


def test_keyframes_and_references_are_mutually_exclusive(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x")
    with pytest.raises(ValueError, match="cannot be mixed"):
        build_h3_content(
            "prompt",
            first_frame=image,
            references=[
                H3Reference(kind="image_url", source=image, role="reference_image")
            ],
        )


def test_reference_role_must_match_media_kind(tmp_path: Path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"x")
    with pytest.raises(ValidationError, match="requires kind=image_url"):
        H3Reference(kind="video_url", source=image, role="reference_image")


def test_reference_count_limits_are_enforced() -> None:
    references = [
        H3Reference(
            kind="image_url",
            source=f"https://example.invalid/{index}.png",
            role="reference_image",
        )
        for index in range(10)
    ]
    with pytest.raises(ValueError, match="count limit"):
        build_h3_content("prompt", references=references)
