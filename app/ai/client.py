# app/ai/client.py
import os
import time
import requests
import logging
import re
from urllib.parse import urlparse
from typing import Any, Callable, Dict, List, Sequence

from app.core.settings import settings

logger = logging.getLogger("ai_client")


def retry_with_backoff(fn: Callable[[], Any], max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
    """
    Retry the callable with exponential backoff for transient failures.
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning("AI client retry %s/%s after %.1fs: %s", attempt + 1, max_retries, delay, exc)
            time.sleep(delay)


class OllamaGenerateClient:
    """
    Super simple Ollama client that ONLY uses /api/generate,
    which we just confirmed is available on your machine.
    """

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: Sequence[Dict[str, Any]], temperature: float = 0, format: str | None = None) -> str:
        """
        messages: list of {role, content}
        We just smash them into one prompt and send to /api/generate.
        """
        if not isinstance(messages, (list, tuple)):
            raise ValueError("messages must be a list/tuple of dicts")
        parts = []
        for m in messages:
            if not isinstance(m, dict):
                raise ValueError("message must be a dict with role/content")
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"{role.upper()}: {content}")
        prompt = "\n".join(parts)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        def _call():
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()

        data = retry_with_backoff(_call)
        # /api/generate returns {"response": "...", ...}
        return data.get("response", "").strip()


class OpenAIChatClient:
    """
    Adapter that exposes a .chat(messages, temperature) interface
    compatible with callers expecting Ollama-like semantics.
    """

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def chat(self, messages: Sequence[Dict[str, Any]], temperature: float = 0, format: str | None = None) -> str:
        if not isinstance(messages, (list, tuple)):
            raise ValueError("messages must be a list/tuple of dicts")

        def _call():
            return self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"} if format == "json" else None,
            )

        resp = retry_with_backoff(_call)
        content = resp.choices[0].message.content if resp.choices else ""
        return (content or "").strip()

    def chat_stream(self, messages: Sequence[Dict[str, Any]], temperature: float = 0, on_chunk=None) -> str:
        """
        Stream a chat completion and optionally invoke a callback per chunk.
        Returns the full aggregated response text.
        """
        if not isinstance(messages, (list, tuple)):
            raise ValueError("messages must be a list/tuple of dicts")

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        full = ""
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content or ""
            except Exception:
                delta = ""
            full += delta
            if on_chunk and delta:
                try:
                    on_chunk(delta)
                except Exception:
                    pass
        return full.strip()


def _validate_ollama_base(base_url: str) -> str:
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid Ollama URL scheme")
    # Restrict to allowed hosts to avoid SSRF
    allowed_hosts_env = os.getenv("OLLAMA_ALLOWED_HOSTS", "")
    if allowed_hosts_env:
        allowed_hosts = {h.strip().lower() for h in allowed_hosts_env.split(",") if h.strip()}
    else:
        allowed_hosts = {"127.0.0.1", "localhost", "::1"}
    if host.lower() not in allowed_hosts:
        raise ValueError("Ollama base URL host not in allowlist")
    return base_url.rstrip("/")


def get_llm_client():
    """
    Build an Ollama or OpenAI client, unless AI is disabled via settings.
    """
    # Global AI toggle: if disabled, return None so all callers fall back
    if not getattr(settings, "AI_ENABLED", True):
        logger.info("[AI client] AI disabled via settings.AI_ENABLED")
        return None

    provider_env = os.getenv("AI_PROVIDER", "").strip().lower()
    provider_setting = (getattr(settings, "ai_provider", None) or "").strip().lower()
    provider = provider_env or provider_setting

    api_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)

    # Auto-detect: if any OpenAI key exists, prefer OpenAI regardless of provider flag.
    if api_key:
        provider = "openai"

    if provider == "openai":
        if not api_key:
            logger.warning("[AI client] OPENAI selected but no key -> rule-based")
            return None
        model = os.getenv("OPENAI_MODEL") or getattr(settings, "openai_model", None) or "gpt-4o-mini"
        logger.info("[AI client] Using OpenAI model=%s", model)
        return OpenAIChatClient(api_key=api_key, model=model)

    # otherwise: default to local Ollama
    base_env = os.getenv("OLLAMA_BASE_URL")
    base_setting = getattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    base = _validate_ollama_base(base_env or base_setting)
    model = os.getenv("OLLAMA_MODEL") or getattr(settings, "ollama_model", "gemma3:4b")  # we saw this in /api/tags

    logger.info("[AI client] Using local Ollama (generate) at %s model=%s", base, model)
    return OllamaGenerateClient(base, model)
