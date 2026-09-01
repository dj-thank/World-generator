from pathlib import Path

from world_generator.export.webxr import export_panorama_viewer, export_splat_viewer


def test_splat_viewer_contains_webxr_and_spark(tmp_path: Path) -> None:
    splat = tmp_path / "input.ply"
    splat.write_text("ply\nformat ascii 1.0\nend_header\n", encoding="utf-8")
    index = export_splat_viewer(splat, tmp_path / "viewer", title="Test world")
    page = index.read_text(encoding="utf-8")
    assert "VRButton" in page
    assert "SparkRenderer" in page
    assert "SplatMesh" in page
    assert (tmp_path / "viewer" / "assets" / "world.ply").is_file()


def test_panorama_viewer_copies_asset(tmp_path: Path) -> None:
    image = tmp_path / "pano.png"
    image.write_bytes(b"fake")
    index = export_panorama_viewer(image, tmp_path / "pano-viewer", title="Pano")
    page = index.read_text(encoding="utf-8")
    assert "SphereGeometry" in page
    assert "VRButton" in page
    assert (tmp_path / "pano-viewer" / "assets" / "panorama.png").is_file()
