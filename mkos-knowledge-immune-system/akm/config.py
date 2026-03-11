"""Configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """AKM configuration."""

    workspace_root: str = ""
    db_path: str = ""
    cockpit_path: str = ""

    # Ingestion
    file_extensions: list[str] = field(default_factory=lambda: [".md", ".json"])
    ignore_patterns: list[str] = field(default_factory=lambda: [
        ".venv", "venv", "node_modules", ".git", "__pycache__",
        ".pytest_cache", ".mypy_cache", ".tmp",
    ])
    max_chunk_tokens: int = 512

    # Search
    max_results: int = 10

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 1024

    # Composting
    entropy_decay_rate: float = 0.01
    composting_threshold: float = 0.7
    composting_archive_originals: bool = True

    # Fermentation
    fermentation_duration_hours: float = 24.0
    fermentation_confidence_threshold: float = 0.6
    fermentation_max_contradictions: int = 2

    # Immune
    immune_scan_sample_size: int = 50
    immune_min_fitness: float = 0.2

    def __post_init__(self) -> None:
        if not self.workspace_root:
            self.workspace_root = os.getenv("AKM_WORKSPACE_ROOT", str(Path.cwd()))
        if not self.db_path:
            self.db_path = str(Path.home() / ".akm" / "knowledge.db")
        if not self.cockpit_path:
            self.cockpit_path = str(Path(self.workspace_root) / "Cockpit" / "data.json")
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not self.openai_api_key:
            self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

    @classmethod
    def from_env(cls, env_path: str | None = None) -> Config:
        load_dotenv(env_path, override=True)
        config = cls()
        config.workspace_root = os.getenv("AKM_WORKSPACE_ROOT", "") or config.workspace_root
        config.db_path = os.getenv("AKM_DB_PATH", "") or config.db_path
        config.cockpit_path = os.getenv("AKM_COCKPIT_PATH", "") or config.cockpit_path
        config.max_chunk_tokens = int(os.getenv("AKM_MAX_CHUNK_TOKENS", str(config.max_chunk_tokens)))
        config.max_results = int(os.getenv("AKM_MAX_RESULTS", str(config.max_results)))
        config.llm_model = os.getenv("AKM_LLM_MODEL", config.llm_model)
        config.entropy_decay_rate = float(os.getenv("AKM_ENTROPY_DECAY_RATE", str(config.entropy_decay_rate)))
        config.composting_threshold = float(os.getenv("AKM_COMPOSTING_THRESHOLD", str(config.composting_threshold)))
        config.fermentation_duration_hours = float(os.getenv("AKM_FERMENTATION_HOURS", str(config.fermentation_duration_hours)))
        config.immune_scan_sample_size = int(os.getenv("AKM_IMMUNE_SAMPLE_SIZE", str(config.immune_scan_sample_size)))
        return config
