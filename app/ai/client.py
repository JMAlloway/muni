# app/ai/client.py
import os
import time
import requests

from app.core.settings import settings


def retry_with_backoff(fn, max_retries: int = 3, base_delay: float = 1.0):
    """
    Retry the callable with exponential backoff for transient failures.
    """
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            try:
                print(f"[AI client] Retry {attempt + 1}/{max_retries} after {delay}s: {exc}")
            except Exception:
                pass
            time.sleep(delay)


class OllamaGenerateClient:
    """
    Super simple Ollama client that ONLY uses /api/generate,
    which we just confirmed is available on your machine.
    """

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages, temperature=0, format=None):
        """
        messages: list of {role, content}
        We just smash them into one prompt and send to /api/generate.
        """
        # turn chat messages into a single prompt
        parts = []
        for m in messages:
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

    def chat(self, messages, temperature=0, format=None):
        try:
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
        except Exception as exc:
            print(f"[AI client] OpenAI chat error: {exc}")
            return ""

    def chat_stream(self, messages, temperature=0, on_chunk=None):
        """
        Stream a chat completion and optionally invoke a callback per chunk.
        Returns the full aggregated response text.
        """
        try:
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
        except Exception as exc:
            print(f"[AI client] OpenAI chat stream error: {exc}")
            return ""


def get_llm_client():
    """
    Build an Ollama or OpenAI client, unless AI is disabled via settings.
    """
    # Global AI toggle: if disabled, return None so all callers fall back
    if not getattr(settings, "AI_ENABLED", True):
        print("[AI client] AI disabled via settings.AI_ENABLED")
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
            print("[AI client] OPENAI selected but no key -> rule-based")
            return None
        model = os.getenv("OPENAI_MODEL") or getattr(settings, "openai_model", None) or "gpt-4o"
        print(f"[AI client] Using OpenAI model={model}")
        return OpenAIChatClient(api_key=api_key, model=model)

    # otherwise: default to local Ollama
    base = os.getenv("OLLAMA_BASE_URL") or getattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL") or getattr(settings, "ollama_model", "gemma3:4b")  # we saw this in /api/tags

    print(f"[AI client] Using local Ollama (generate) at {base} model={model}")
    return OllamaGenerateClient(base, model)
