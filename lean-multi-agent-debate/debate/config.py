"""
Lean Multi-Agent Debate Engine — Configuration
Loaded from .env via Pydantic Settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Keys
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Model IDs
    gemini_thinking_model: str = "gemini-3.1-pro-preview"  # Phase 1a (CoT) + Phase 2b (verify) — deep reasoning
    gemini_pro_model: str = "gemini-2.5-flash"              # Phase 1b (facts/RAG) — fast, cost-efficient
    claude_model: str = "claude-opus-4-6"                   # Phase 2a (critique) + Phase 3 (final)

    # Token budgets
    max_tokens_phase1: int = 8192
    max_tokens_critique: int = 4096
    max_tokens_final: int = 4096


settings = Settings()
