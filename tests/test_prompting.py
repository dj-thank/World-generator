from world_generator.models import CameraPath, WorldSpec
from world_generator.prompting import build_world_ir, compile_prompts


def test_h3_prompt_is_reconstruction_constrained() -> None:
    spec = WorldSpec(
        prompt="A quiet stone courtyard",
        camera_path=CameraPath.ARC_CLOCKWISE,
        duration_seconds=8,
    )
    prompts = compile_prompts(spec)
    assert "For the target video, at 0.00 seconds" in prompts.h3_video
    assert "integrated_multimodal_description: [Shot 1]" in prompts.h3_video
    assert "single continuous reconstruction capture" in prompts.h3_video
    assert "The shot never cuts" in prompts.h3_video
    assert "fixed 24–28 mm" in prompts.h3_video
    assert "non_diegetic_music: N/A" in prompts.h3_video


def test_world_ir_preserves_camera_plan() -> None:
    spec = WorldSpec(
        prompt="A quiet stone courtyard",
        orbit_degrees=55,
        duration_seconds=12,
    )
    ir = build_world_ir(spec)
    assert ir.camera.approximate_degrees == 55
    assert ir.camera.duration_seconds == 12
    assert ir.camera.continuous_shot is True
    assert any("COLMAP" in target for target in ir.reconstruction_targets)


def test_text_to_video_prompt_omits_picture_instruction() -> None:
    prompts = compile_prompts(
        WorldSpec(prompt="A static observatory"),
        has_first_frame=False,
    )
    assert not prompts.h3_video.startswith("For the target video")
    assert "integrated_multimodal_description" in prompts.h3_video
