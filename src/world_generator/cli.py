from __future__ import annotations

import shutil
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings
from .models import AspectRatio, CameraPath, H3Resolution, WorldSpec
from .pipeline import WorldGenerationPipeline
from .providers.minimax_h3 import MiniMaxH3Client
from .providers.openai_images import OpenAIImageProvider
from .reconstruction.nerfstudio import NerfstudioReconstructor

app = typer.Typer(
    no_args_is_help=True,
    help="Generate VR-ready worlds with image models, MiniMax H3, Gaussian Splatting, and WebXR.",
)
console = Console()


@app.command()
def generate(
    prompt: str = typer.Argument(..., help="World description in Japanese or English."),
    output: Path = typer.Option(Path("outputs/world"), "--output", "-o"),
    name: str = typer.Option("generated-world", "--name"),
    anchor_image: Path | None = typer.Option(
        None,
        "--anchor-image",
        exists=True,
        dir_okay=False,
    ),
    panorama_image: Path | None = typer.Option(
        None,
        "--panorama-image",
        exists=True,
        dir_okay=False,
    ),
    duration: int = typer.Option(10, min=4, max=15),
    resolution: H3Resolution = typer.Option(H3Resolution.P768),
    ratio: AspectRatio = typer.Option(AspectRatio.WIDE),
    camera_path: CameraPath = typer.Option(CameraPath.ARC_CLOCKWISE),
    orbit_degrees: int = typer.Option(45, min=10, max=90),
    camera_height: float = typer.Option(1.65, min=0.5, max=3.0),
    image_quality: str | None = typer.Option(None),
    use_context_ir: bool = typer.Option(False, "--use-context-ir/--no-context-ir"),
    panorama_only: bool = typer.Option(False, "--panorama-only"),
    no_panorama: bool = typer.Option(False, "--no-panorama"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    strict_reconstruction: bool = typer.Option(False, "--strict-reconstruction"),
    max_training_iterations: int | None = typer.Option(None, min=100),
) -> None:
    """Run the complete text/image → H3 → Gaussian Splat → WebXR pipeline."""
    if panorama_only and no_panorama and panorama_image is None:
        raise typer.BadParameter(
            "--panorama-only cannot be combined with --no-panorama without --panorama-image."
        )
    settings = Settings()
    spec = WorldSpec(
        name=name,
        prompt=prompt,
        duration_seconds=duration,
        resolution=resolution,
        ratio=ratio,
        camera_path=camera_path,
        orbit_degrees=orbit_degrees,
        camera_height_m=camera_height,
        image_quality=image_quality or settings.openai_image_quality,
        use_context_ir=use_context_ir,
        generate_panorama=not no_panorama,
        strict_reconstruction=strict_reconstruction,
        max_training_iterations=max_training_iterations,
    )
    image_provider = None if dry_run else OpenAIImageProvider(settings)
    h3_client = None if dry_run or panorama_only else MiniMaxH3Client(settings)
    reconstructor = None if dry_run or panorama_only else NerfstudioReconstructor(settings)
    pipeline = WorldGenerationPipeline(
        image_provider=image_provider,
        video_provider=h3_client,
        reconstructor=reconstructor,
        ffmpeg_bin=settings.ffmpeg_bin,
    )
    try:
        manifest = pipeline.run(
            spec,
            output,
            anchor_image=anchor_image,
            panorama_image=panorama_image,
            dry_run=dry_run,
            panorama_only=panorama_only,
        )
    except Exception as exc:
        console.print(f"[bold red]Generation failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc
    finally:
        if h3_client is not None:
            h3_client.close()

    console.print(f"[bold green]Status:[/bold green] {manifest.status.value}")
    console.print(f"Manifest: {output.resolve() / 'manifest.json'}")
    if "splat_viewer" in manifest.artifacts:
        console.print(f"Splat viewer: {output.resolve() / 'viewer-splat' / 'index.html'}")
    if "panorama_viewer" in manifest.artifacts:
        console.print(
            f"Panorama viewer: {output.resolve() / 'viewer-panorama' / 'index.html'}"
        )


@app.command()
def reconstruct(
    video: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(Path("outputs/reconstructed"), "--output", "-o"),
    max_training_iterations: int | None = typer.Option(None, min=100),
) -> None:
    """Reconstruct an existing camera-motion video into a Gaussian Splat viewer."""
    settings = Settings()
    pipeline = WorldGenerationPipeline(
        image_provider=None,
        video_provider=None,
        reconstructor=NerfstudioReconstructor(settings),
        ffmpeg_bin=settings.ffmpeg_bin,
    )
    try:
        splat = pipeline.reconstruct_existing(
            video,
            output,
            max_iterations=max_training_iterations,
        )
    except Exception as exc:
        console.print(f"[bold red]Reconstruction failed:[/bold red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[bold green]Exported:[/bold green] {splat}")
    console.print(f"Viewer: {output.resolve() / 'viewer-splat' / 'index.html'}")


@app.command()
def doctor() -> None:
    """Check credentials and local reconstruction executables."""
    settings = Settings()
    table = Table(title="World Generator environment")
    table.add_column("Component")
    table.add_column("Status")
    table.add_row(
        "OPENAI_API_KEY",
        "configured" if settings.openai_api_key else "missing",
    )
    table.add_row(
        "MINIMAX_API_KEY",
        "configured" if settings.minimax_api_key else "missing",
    )
    for label, executable in [
        ("FFmpeg", settings.ffmpeg_bin),
        ("COLMAP", settings.colmap_bin),
        ("Nerfstudio process", settings.ns_process_data_bin),
        ("Nerfstudio train", settings.ns_train_bin),
        ("Nerfstudio export", settings.ns_export_bin),
    ]:
        resolved = shutil.which(executable)
        table.add_row(label, resolved or "missing")
    console.print(table)


@app.command()
def serve(
    directory: Path = typer.Argument(..., exists=True, file_okay=False),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000, min=1, max=65535),
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser"),
) -> None:
    """Serve a generated WebXR directory over HTTP."""
    root = directory.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    console.print(f"Serving [bold]{root}[/bold] at [link={url}]{url}[/link]")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("Stopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    app()
