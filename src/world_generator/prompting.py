from __future__ import annotations

from pydantic import BaseModel

from .models import CameraPath, CameraPlan, WorldIR, WorldSpec


class PromptBundle(BaseModel):
    anchor_image: str
    panorama_image: str
    h3_video: str


_MOVEMENTS: dict[CameraPath, str] = {
    CameraPath.ARC_CLOCKWISE: "performs a smooth clockwise Arc Shot around the scene center",
    CameraPath.ARC_COUNTERCLOCKWISE: (
        "performs a smooth counterclockwise Arc Shot around the scene center"
    ),
    CameraPath.TRUCK_RIGHT: "trucks right along a straight, level path",
    CameraPath.TRUCK_LEFT: "trucks left along a straight, level path",
    CameraPath.PUSH_IN: "pushes in slowly along the central navigable path",
}


def build_world_ir(spec: WorldSpec) -> WorldIR:
    return WorldIR(
        world_name=spec.name,
        scene_intent=spec.prompt,
        visual_style=spec.style,
        immutable_geometry=[
            "All walls, floors, ceilings, doors, windows, terrain, furniture, and props keep fixed shape and position.",
            "Object identity, object count, scale, materials, texture placement, and lighting remain unchanged.",
            "No geometry appears, disappears, stretches, melts, duplicates, or changes topology.",
        ],
        navigable_regions=[
            "Keep a clear human-scale floor region around the camera path.",
            "Maintain plausible metric scale and unobstructed head-height visibility.",
            "Do not place moving subjects across the capture path.",
        ],
        camera=CameraPlan(
            movement=spec.camera_path,
            approximate_degrees=spec.orbit_degrees,
            duration_seconds=spec.duration_seconds,
            height_m=spec.camera_height_m,
        ),
        generation_constraints=[
            "One continuous shot; no cuts, transitions, time jumps, or scene changes.",
            "Fixed focal length, focus distance, exposure, white balance, and lighting.",
            "Slow constant camera speed with strong frame overlap and visible parallax.",
            "No people, animals, vehicles, smoke, flowing water, cloth motion, particles, or animated screens unless explicitly requested.",
            "No zoom, lens breathing, rolling shutter, camera shake, motion blur, or depth-of-field pulsing.",
        ],
        reconstruction_targets=[
            "Recover stable camera poses with COLMAP.",
            "Train a Nerfstudio Splatfacto scene and export a Gaussian Splat PLY.",
            "Preserve a 360-degree panorama fallback for WebXR viewing.",
        ],
    )


def compile_prompts(spec: WorldSpec, *, has_first_frame: bool = True) -> PromptBundle:
    movement = _MOVEMENTS[spec.camera_path]
    shared_scene = (
        f"World concept: {spec.prompt}\n"
        f"Visual style: {spec.style}.\n"
        "Treat this as a canonical, physically coherent world state that must remain reconstructable "
        "from nearby camera viewpoints."
    )

    anchor = f"""Create one canonical perspective image for a VR world reconstruction pipeline.
{shared_scene}

Composition and geometry requirements:
- Landscape framing with a natural human eye height of approximately {spec.camera_height_m:.2f} meters.
- A 24–28 mm full-frame-equivalent lens, level horizon, deep focus, and low distortion.
- A clear, traversable floor or ground region in the center and foreground.
- Strong static visual features and texture detail across near, middle, and far depth planes.
- Occluding edges and repeated structural anchors that will remain recognizable from adjacent viewpoints.
- Plausible metric scale, physically consistent perspective, stable lighting, and stable materials.
- No people, animals, moving vehicles, smoke, fire, flowing water, animated displays, floating particles, text, logos, or watermarks.
- Do not use fisheye projection, motion blur, shallow depth of field, extreme bloom, or impossible geometry.

This is the immutable first frame for a slow camera capture. Every object must be suitable for remaining exactly fixed while only the camera moves."""

    panorama = f"""Create a seamless equirectangular 360-degree panorama for a WebXR environment.
{shared_scene}

Projection requirements:
- Exact 2:1 equirectangular panorama covering 360 degrees horizontally and 180 degrees vertically.
- Seamless left and right edges; continuous ceiling/sky at the top and floor/ground at the bottom.
- Camera at approximately {spec.camera_height_m:.2f} meters with a level horizon at the vertical midpoint.
- Stable physically plausible geometry, lighting, scale, and materials in every direction.
- Preserve one clearly navigable central area and coherent entrances, walls, terrain, and objects.
- No people, moving objects, text, logos, watermarks, cubemap cross layout, fisheye circle, or duplicated seams."""

    alignment = ""
    first_frame_reference = "the world established by the textual concept"
    if has_first_frame:
        alignment = (
            "For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        )
        first_frame_reference = (
            "<Picture 1>, preserving its architecture, layout, object identity, object count, "
            "materials, illumination, perspective anchors, and human-scale proportions"
        )

    h3 = f"""{alignment}integrated_multimodal_description: [Shot 1] {spec.style}, a single continuous reconstruction capture begins from {first_frame_reference}. The entire environment is completely static. The camera is held at approximately {spec.camera_height_m:.2f} meters, keeps a fixed 24–28 mm equivalent focal length, fixed focus, fixed exposure, fixed white balance, and a level horizon. Over the full {spec.duration_seconds}.00-second shot, the camera {movement} over approximately {spec.orbit_degrees} degrees at slow constant speed with medium-small amplitude, producing strong overlap and natural parallax among foreground, midground, and background features. The shot never cuts and never changes scene. Walls, floors, ceilings, terrain, doors, windows, furniture, props, object count, geometry, scale, materials, textures, shadows, and light sources remain exactly fixed from frame to frame. No subject enters the scene. Nothing morphs, stretches, melts, duplicates, flickers, appears, disappears, or changes topology. There is no zoom, lens breathing, focus pull, exposure shift, camera shake, rolling shutter, motion blur, time jump, animation, moving screen content, smoke, particles, cloth motion, vegetation motion, or flowing liquid. The final frame remains a plausible nearby view of the same immutable world and exposes additional side surfaces through camera parallax only.

overall_soundscape: A low, steady environmental room tone remains consistent throughout, with no speech and no moving-source sound.

non_diegetic_music: N/A"""

    return PromptBundle(anchor_image=anchor, panorama_image=panorama, h3_video=h3)
