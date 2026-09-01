from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel

from ..config import Settings
from ..errors import ConfigurationError, ReconstructionError
from ..media import copy_media, run_logged


class ReconstructionResult(BaseModel):
    splat_path: Path
    processed_dir: Path
    training_dir: Path
    export_dir: Path
    config_path: Path


class NerfstudioReconstructor:
    """Run COLMAP-backed Nerfstudio preprocessing, Splatfacto training, and PLY export."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def missing_tools(self) -> list[str]:
        required = [
            self.settings.ffmpeg_bin,
            self.settings.colmap_bin,
            self.settings.ns_process_data_bin,
            self.settings.ns_train_bin,
            self.settings.ns_export_bin,
        ]
        return [tool for tool in required if shutil.which(tool) is None]

    def build_process_command(self, video: Path, processed_dir: Path) -> list[str]:
        return [
            self.settings.ns_process_data_bin,
            "video",
            "--data",
            str(video),
            "--output-dir",
            str(processed_dir),
        ]

    def build_train_command(
        self,
        processed_dir: Path,
        training_dir: Path,
        *,
        max_iterations: int | None,
    ) -> list[str]:
        command = [
            self.settings.ns_train_bin,
            "splatfacto",
            "--data",
            str(processed_dir),
            "--output-dir",
            str(training_dir),
            "--viewer.quit-on-train-completion",
            "True",
        ]
        if max_iterations is not None:
            command.extend(["--max-num-iterations", str(max_iterations)])
        return command

    def build_export_command(self, config_path: Path, export_dir: Path) -> list[str]:
        return [
            self.settings.ns_export_bin,
            "gaussian-splat",
            "--load-config",
            str(config_path),
            "--output-dir",
            str(export_dir),
        ]

    def reconstruct(
        self,
        video: Path,
        output_dir: Path,
        *,
        max_iterations: int | None = None,
    ) -> ReconstructionResult:
        if not video.is_file():
            raise FileNotFoundError(video)
        missing = self.missing_tools()
        if missing:
            raise ConfigurationError(
                "Missing reconstruction executables: " + ", ".join(missing)
            )

        processed = output_dir / "processed"
        training = output_dir / "training"
        exported = output_dir / "export"
        logs = output_dir / "logs"
        for directory in (processed, training, exported, logs):
            directory.mkdir(parents=True, exist_ok=True)

        run_logged(
            self.build_process_command(video, processed),
            log_path=logs / "01-process-data.log",
        )
        run_logged(
            self.build_train_command(
                processed, training, max_iterations=max_iterations
            ),
            log_path=logs / "02-train-splatfacto.log",
        )

        configs = sorted(
            [*training.rglob("config.yml"), *training.rglob("config.yaml")],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not configs:
            raise ReconstructionError(
                f"Nerfstudio training completed but no config.yml was found under {training}."
            )
        config = configs[0]
        run_logged(
            self.build_export_command(config, exported),
            log_path=logs / "03-export-splat.log",
        )

        candidates = sorted(
            exported.rglob("*.ply"),
            key=lambda path: path.stat().st_size,
            reverse=True,
        )
        if not candidates:
            raise ReconstructionError(
                f"Nerfstudio export completed but no .ply was found under {exported}."
            )
        final_splat = copy_media(candidates[0], output_dir / "world.ply")
        return ReconstructionResult(
            splat_path=final_splat,
            processed_dir=processed,
            training_dir=training,
            export_dir=exported,
            config_path=config,
        )
