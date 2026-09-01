from pathlib import Path

import pytest

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
    item = payload["content"][1]
    assert item["type"] == "image_url"
    assert item["role"] == "first_frame"
    assert item["image_url"]["url"].startswith("data:image/png;base64,")


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
