from __future__ import annotations

import base64
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx

from .errors import ExternalCommandError, ProviderError


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, value: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_media(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    ensure_parent(destination)
    shutil.copy2(source, destination)
    return destination


def path_to_data_url(path: Path, *, max_bytes: int) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size > max_bytes:
        raise ProviderError(
            f"{path} is {size:,} bytes; inline limit is {max_bytes:,}. "
            "Upload it to a short-lived public URL and pass that URL instead."
        )
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def media_source_to_url(source: str | Path, *, max_bytes: int) -> str:
    value = str(source)
    if value.startswith(("https://", "http://", "data:")):
        return value
    return path_to_data_url(Path(value), max_bytes=max_bytes)


def download_file(url: str, destination: Path, *, timeout: float = 180.0) -> Path:
    ensure_parent(destination)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    except (httpx.HTTPError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise ProviderError(f"Failed to download generated asset: {exc}") from exc
    return destination


def run_logged(command: list[str], *, log_path: Path, cwd: Path | None = None) -> None:
    ensure_parent(log_path)
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout or "").splitlines()[-20:])
        raise ExternalCommandError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}\n{tail}"
        )


def extract_first_frame(video: Path, destination: Path, *, ffmpeg_bin: str) -> Path:
    ensure_parent(destination)
    run_logged(
        [ffmpeg_bin, "-y", "-ss", "0", "-i", str(video), "-frames:v", "1", str(destination)],
        log_path=destination.parent / "extract-first-frame.log",
    )
    return destination
