from __future__ import annotations

import base64
import contextlib
import hashlib
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_data_dir: str = "/data"
    demo_mode: bool = False
    api_key: str = ""
    sync_interval_minutes: int = 60
    secret_key: str = ""
    static_dir: str = ""

    # LLM (OpenAI-compatible; default DeepSeek Flash)
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-flash"
    llm_use_responses_api: bool = True

    # Mealie (Optional, read-only)
    mealie_url: str = ""
    mealie_api_token: str = ""

    @property
    def data_path(self) -> Path:
        path = Path(self.app_data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def db_path(self) -> Path:
        return self.data_path / "app.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def image_cache_dir(self) -> Path:
        path = self.data_path / "cache" / "mealie_images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def picnic_image_cache_dir(self) -> Path:
        path = self.data_path / "cache" / "picnic_images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_fernet(self) -> Fernet:
        """Return a Fernet instance backed by SECRET_KEY env or a persisted key in APP_DATA_DIR."""
        raw_key: bytes
        if self.secret_key:
            digest = hashlib.sha256(self.secret_key.encode("utf-8")).digest()
            raw_key = base64.urlsafe_b64encode(digest)
        else:
            key_file = self.data_path / ".secret.key"
            if key_file.exists():
                raw_key = key_file.read_bytes().strip()
            else:
                raw_key = Fernet.generate_key()
                key_file.write_bytes(raw_key)
                with contextlib.suppress(OSError):
                    os.chmod(key_file, 0o600)
        return Fernet(raw_key)

    def encrypt_secret(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        token = self.get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    def decrypt_secret(self, value: str | None) -> str:
        if not value:
            return ""
        if value.startswith("enc:"):
            try:
                return self.get_fernet().decrypt(value[4:].encode("utf-8")).decode("utf-8")
            except InvalidToken:
                return ""
        return value


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "••••••"
    return f"{value[:3]}••••{value[-3:]}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
