"""Explicit, bounded settings for the single-user local application."""

from dataclasses import dataclass, field
import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PACKAGE_ROOT.parents[1]


@dataclass(frozen=True)
class Settings:
    max_upload_bytes: int = 20 * 1024 * 1024
    max_acv_upload_bytes: int = 64 * 1024 * 1024
    max_rows: int = 300_000
    analysis_ttl_seconds: float = 30 * 60
    max_analyses: int = 3
    model_directory: Path = field(default_factory=lambda: PACKAGE_ROOT / "models")
    frontend_directory: Path = field(default_factory=lambda: APP_ROOT / "frontend" / "out")
    dev_origins: tuple[str, ...] = ("http://127.0.0.1:3000", "http://localhost:3000")

    def __post_init__(self):
        import math

        if self.max_upload_bytes <= 0 or self.max_rows <= 0 or self.max_analyses <= 0:
            raise ValueError("Upload, row, and analysis-count limits must be positive.")
        if not math.isfinite(self.analysis_ttl_seconds) or self.analysis_ttl_seconds <= 0:
            raise ValueError("Analysis lifetime must be positive and finite.")

    @classmethod
    def from_env(cls):
        values = {}
        conversions = {
            "MAX_UPLOAD_BYTES": ("max_upload_bytes", int),
            "MAX_ACV_UPLOAD_BYTES": ("max_acv_upload_bytes", int),
            "MAX_ROWS": ("max_rows", int),
            "ANALYSIS_TTL_SECONDS": ("analysis_ttl_seconds", float),
            "MAX_ANALYSES": ("max_analyses", int),
            "MODEL_DIRECTORY": ("model_directory", Path),
            "FRONTEND_DIRECTORY": ("frontend_directory", Path),
        }
        for suffix, (name, convert) in conversions.items():
            value = os.environ.get(f"DOORLENS_{suffix}")
            if value is not None:
                values[name] = convert(value)
        return cls(**values)
