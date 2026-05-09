"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ------------------------------------------------------------------
    app_name: str = "AI WhatsApp Software Engineer"
    environment: str = Field(default="development")
    debug: bool = True
    api_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"

    # --- Security -------------------------------------------------------------
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # CORS
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- MongoDB --------------------------------------------------------------
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "ai_wa_engineer"

    # --- Redis ----------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- WAHA -----------------------------------------------------------------
    waha_base_url: str = "http://localhost:3000"
    waha_api_key: Optional[str] = None
    waha_session: str = "default"
    waha_webhook_secret: Optional[str] = None
    # Allow webhook messages sent by the same connected WAHA account.
    # Useful for local testing when you chat from your own number.
    waha_accept_from_me: bool = False

    # --- AI provider ----------------------------------------------------------
    # auto = use Azure if AZURE_OPENAI_ENDPOINT+KEY set, else OpenAI-compatible key
    # openai = always OpenAI-compatible client (Groq, Ollama, LM Studio, OpenAI, …)
    # azure = force Azure (must set AZURE_*)
    llm_provider: str = "auto"

    # --- AI / OpenAI (platform.openai.com) ------------------------------------
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # e.g. Groq https://api.groq.com/openai/v1 or Ollama http://host:11434/v1
    openai_model: str = "gpt-4o-mini"
    openai_embeddings_model: str = "text-embedding-3-small"
    # One LLM round per tool in JSON protocol (Ollama/local); branches+edit+push+PR+finish exhausts ~6–15 quickly.
    ai_max_tool_iterations: int = Field(default=20, ge=1, le=200)
    # auto = disable OpenAI tools= for Ollama/local URLs (use JSON tool protocol in orchestrator)
    llm_native_tools: str = "auto"

    # --- Azure OpenAI (optional — takes precedence when endpoint + key are set)
    # Env: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION,
    #      AZURE_OPENAI_DEPLOYMENT (chat), AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT (optional)
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_api_version: str = "2024-12-01-preview"
    azure_openai_deployment: Optional[str] = None  # Must match your Azure deployment name
    azure_openai_embeddings_deployment: Optional[str] = None  # Separate embedding deployment in Azure

    # --- GitHub ---------------------------------------------------------------
    github_token: Optional[str] = None
    github_default_org: Optional[str] = None

    # --- Workspace ------------------------------------------------------------
    # Where cloned repositories will live (sandboxed root).
    workspace_root: str = "/tmp/ai-wa-workspaces"

    # --- Approvals ------------------------------------------------------------
    require_approval_for_push: bool = True
    require_approval_for_deploy: bool = True

    @field_validator("openai_base_url", mode="before")
    @classmethod
    def normalize_openai_base_url(cls, v: object) -> Optional[str]:
        """Empty or invalid base URLs break httpx ('missing http://'). Fix common .env mistakes."""
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        s = v.strip()
        if not s:
            return None
        if not s.lower().startswith(("http://", "https://")):
            s = f"https://{s.lstrip('/')}"
        return s.rstrip("/")

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "auto"
        s = str(v).strip().lower()
        if s not in ("auto", "azure", "openai"):
            return "auto"
        return s

    @field_validator("llm_native_tools", mode="before")
    @classmethod
    def normalize_llm_native_tools(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "auto"
        s = str(v).strip().lower()
        if s not in ("auto", "true", "false"):
            return "auto"
        return s

    @field_validator("azure_openai_endpoint", mode="before")
    @classmethod
    def normalize_azure_endpoint(cls, v: object) -> Optional[str]:
        if v is None or not isinstance(v, str):
            return None
        s = v.strip()
        if not s:
            return None
        if not s.lower().startswith(("http://", "https://")):
            s = f"https://{s.lstrip('/')}"
        return s.rstrip("/")


def openai_client_kwargs(api_key: str) -> dict[str, Any]:
    """Build kwargs for `openai.AsyncOpenAI` — omit base_url when unset so the SDK uses api.openai.com."""
    s = get_settings()
    kw: dict[str, Any] = {"api_key": api_key}
    if s.openai_base_url:
        kw["base_url"] = s.openai_base_url
    return kw


def uses_azure_openai(settings: Optional[Settings] = None) -> bool:
    """True when requests should go to Azure OpenAI (deployment-based)."""
    s = settings or get_settings()
    if s.llm_provider == "openai":
        return False
    if s.llm_provider == "azure":
        return True
    return bool(s.azure_openai_endpoint and s.azure_openai_api_key)


def llm_is_configured(settings: Optional[Settings] = None) -> bool:
    s = settings or get_settings()
    if s.llm_provider == "openai":
        return bool(s.openai_api_key)
    if s.llm_provider == "azure":
        return bool(s.azure_openai_endpoint and s.azure_openai_api_key)
    return bool(s.openai_api_key) or bool(s.azure_openai_endpoint and s.azure_openai_api_key)


def llm_chat_model(settings: Optional[Settings] = None) -> str:
    """Model id (OpenAI-compatible) or deployment name (Azure)."""
    s = settings or get_settings()
    if uses_azure_openai(s):
        dep = (s.azure_openai_deployment or "").strip()
        return dep or s.openai_model
    return s.openai_model


_OPENAI_DEFAULT_EMBEDDING_NAMES = frozenset(
    {"text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"}
)


def openai_base_url_looks_like_ollama(settings: Optional[Settings] = None) -> bool:
    """Ollama exposes OpenAI-compatible API on :11434 (often /v1); embeddings model names differ."""
    url = ((settings or get_settings()).openai_base_url or "").lower()
    return bool(url and ("11434" in url or "ollama" in url))


def llm_embeddings_model(settings: Optional[Settings] = None) -> str:
    """Embedding model id (OpenAI-compatible) or embedding deployment name (Azure)."""
    s = settings or get_settings()
    if uses_azure_openai(s):
        dep = (s.azure_openai_embeddings_deployment or "").strip()
        return dep or s.openai_embeddings_model
    model = (s.openai_embeddings_model or "").strip() or "text-embedding-3-small"
    # Ollama does not ship OpenAI embedding IDs — avoid 404 "model not found, try pulling it first".
    if openai_base_url_looks_like_ollama(s) and model in _OPENAI_DEFAULT_EMBEDDING_NAMES:
        return "nomic-embed-text"
    return model


def should_use_native_openai_tools(settings: Optional[Settings] = None) -> bool:
    """Use OpenAI chat.completions tools= API (GPT-class). False → JSON tool protocol (Ollama-friendly)."""
    s = settings or get_settings()
    mode = (s.llm_native_tools or "auto").strip().lower()
    if mode == "false":
        return False
    if mode == "true":
        return True
    if openai_base_url_looks_like_ollama(s):
        return False
    return True


def get_async_openai_client():
    """Azure OpenAI, or OpenAI-compatible (OpenAI, Groq, Ollama, etc.)."""
    from openai import AsyncAzureOpenAI, AsyncOpenAI

    s = get_settings()

    if s.llm_provider == "openai":
        if not s.openai_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY "
                "(use a dummy value like 'ollama' if the server ignores it)."
            )
        return AsyncOpenAI(**openai_client_kwargs(s.openai_api_key))

    if s.llm_provider == "azure":
        if not (s.azure_openai_endpoint and s.azure_openai_api_key):
            raise RuntimeError("LLM_PROVIDER=azure requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY.")
        return AsyncAzureOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            api_version=s.azure_openai_api_version,
        )

    # auto
    if s.azure_openai_endpoint and s.azure_openai_api_key:
        return AsyncAzureOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            api_version=s.azure_openai_api_version,
        )
    if not s.openai_api_key:
        raise RuntimeError(
            "Set OPENAI_API_KEY (+ optional OPENAI_BASE_URL for Groq/Ollama), "
            "or Azure OpenAI (AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY). "
            "Or set LLM_PROVIDER=openai with a free OpenAI-compatible provider."
        )
    return AsyncOpenAI(**openai_client_kwargs(s.openai_api_key))


@lru_cache
def get_settings() -> Settings:
    return Settings()
