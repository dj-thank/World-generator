from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: SecretStr | None = None
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: str = "medium"

    minimax_api_key: SecretStr | None = None
    minimax_base_url: str = "https://api.minimax.io"
    minimax_model: str = "MiniMax-H3"
    minimax_poll_interval_seconds: float = 10.0
    minimax_request_timeout_seconds: float = 60.0
    minimax_task_timeout_seconds: float = 2400.0
    minimax_http_retries: int = 3
    minimax_max_inline_media_bytes: int = 20_000_000

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    colmap_bin: str = "colmap"
    ns_process_data_bin: str = "ns-process-data"
    ns_train_bin: str = "ns-train"
    ns_export_bin: str = "ns-export"

    def openai_key(self) -> str:
        if self.openai_api_key is None:
            raise ConfigurationError("OPENAI_API_KEY is required to generate missing images.")
        return self.openai_api_key.get_secret_value()

    def minimax_key(self) -> str:
        if self.minimax_api_key is None:
            raise ConfigurationError("MINIMAX_API_KEY is required to generate H3 video.")
        return self.minimax_api_key.get_secret_value()
