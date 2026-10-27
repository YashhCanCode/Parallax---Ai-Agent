"""Runtime configuration, read from environment variables (and an optional .env file).

Secrets never live in code. See `.env.example` at the repository root.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env", override=False)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Data mode: "sample" (offline fixtures), "sec_direct" (live SEC EDGAR API),
    # "zetaris" (SEC EDGAR federated through your Zetaris instance).
    # SAMPLE_MODE=true forces sample mode, so the app runs with nothing connected.
    data_mode: str = field(
        default_factory=lambda: "sample" if _bool("SAMPLE_MODE") else _env("FINSIGHT_DATA_MODE", "zetaris")
    )
    # When true and data_mode == "zetaris", also fetch the same facts directly from
    # SEC and reconcile the two (Zetaris's own docs recommend this row-count check).
    zetaris_cross_check: bool = field(default_factory=lambda: _bool("FINSIGHT_ZETARIS_CROSS_CHECK", True))

    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'backend' / 'finsight.db'}")
    )
    cache_dir: Path = field(default_factory=lambda: Path(_env("FINSIGHT_CACHE_DIR", str(REPO_ROOT / ".cache"))))
    sample_dir: Path = field(default_factory=lambda: REPO_ROOT / "sample_data")

    # SEC requires a declared User-Agent: "app_name contact@email".
    sec_user_agent: str = field(default_factory=lambda: _env("SEC_USER_AGENT") or _env("ZETARIS_USER_AGENT"))

    # Zetaris (UI proxy HTTP API, as documented in github.com/zetaris/getting-started).
    zetaris_base_url: str = field(default_factory=lambda: _env("ZETARIS_BASE_URL", "http://localhost:3000").rstrip("/"))
    zetaris_org_id: str = field(default_factory=lambda: _env("ZETARIS_ORG_ID"))
    zetaris_api_key: str = field(default_factory=lambda: _env("ZETARIS_API_KEY"))
    zetaris_username: str = field(default_factory=lambda: _env("ZETARIS_USERNAME"))
    zetaris_password: str = field(default_factory=lambda: _env("ZETARIS_PASSWORD"))
    zetaris_engine_id: str = field(default_factory=lambda: _env("ZETARIS_ENGINE_ID"))
    zetaris_query_limit: int = field(default_factory=lambda: int(_env("ZETARIS_QUERY_LIMIT", "1000") or 1000))
    zetaris_lightning_db: str = field(default_factory=lambda: _env("ZETARIS_LIGHTNING_DB", "FINSIGHT_SEC"))
    # Register a company's SEC sources in Zetaris the first time it is looked up in zetaris mode.
    zetaris_auto_register: bool = field(default_factory=lambda: _bool("ZETARIS_AUTO_REGISTER", True))
    zetaris_container: str = field(default_factory=lambda: _env("ZETARIS_SCHEMASTORE_CONTAINER", "finsight"))

    # Meterless H-MEM sidecar (services/hmem-sidecar).
    hmem_url: str = field(default_factory=lambda: _env("HMEM_URL", "http://127.0.0.1:8765").rstrip("/"))
    hmem_enabled: bool = field(default_factory=lambda: _bool("HMEM_ENABLED", True))

    # Model provider: "auto" / "meterless" (Meterless Nightshift) or "none" (answers written in code).
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))
    # Meterless Runtime (Nightshift; OpenAI-compatible), contract 0.90.0.
    meterless_base_url: str = field(default_factory=lambda: _env("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1"))
    meterless_token: str = field(default_factory=lambda: _env("METERLESS_RUNTIME_TOKEN"))
    meterless_token_file: str = field(default_factory=lambda: _env("METERLESS_TOKEN_FILE"))
    # NVIDIA Nemotron, routed by Nightshift (connect NVIDIA in Nightshift). meterless/* routing modes also work.
    meterless_model: str = field(default_factory=lambda: _env("METERLESS_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"))

    # Re-check the watchlist automatically every N minutes (0 = only when asked).
    watchlist_check_minutes: int = field(default_factory=lambda: int(_env("WATCHLIST_CHECK_MINUTES", "0") or 0))

    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174"))


def get_settings() -> Settings:
    return Settings()
