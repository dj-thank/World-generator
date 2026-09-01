from pathlib import Path

from world_generator.config import Settings
from world_generator.reconstruction.nerfstudio import NerfstudioReconstructor


def test_nerfstudio_command_shapes() -> None:
    reconstructor = NerfstudioReconstructor(Settings(_env_file=None))
    process = reconstructor.build_process_command(Path("clip.mp4"), Path("processed"))
    train = reconstructor.build_train_command(
        Path("processed"),
        Path("training"),
        max_iterations=2000,
    )
    export = reconstructor.build_export_command(Path("config.yml"), Path("export"))
    assert process[:2] == ["ns-process-data", "video"]
    assert train[:2] == ["ns-train", "splatfacto"]
    assert "--max-num-iterations" in train
    assert export[:2] == ["ns-export", "gaussian-splat"]
