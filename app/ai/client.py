# app/ai/client.py
import os
import requests

from app.core.settings import settings


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

        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        # /api/generate returns {"response": "...", ...}
        return data.get("response", "").strip()


def get_llm_client():
    """
    Build an Ollama or OpenAI client, unless AI is disabled via settings.
    """
    # 🔥 Global AI toggle: if disabled, return None so all callers fall back
    if not getattr(settings, "AI_ENABLED", True):
        print("[AI client] AI disabled via settings.AI_ENABLED")
        return None

    provider = os.getenv("AI_PROVIDER", "").lower().strip()

    # if someone explicitly wants OpenAI, honor it
    if provider == "openai":
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[AI client] OPENAI selected but no key -> rule-based")
            return None
        print("[AI client] Using OpenAI")
        return OpenAI(api_key=api_key)

    # otherwise: default to local Ollama
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "gemma3:4b")  # we saw this in /api/tags

    print(f"[AI client] Using local Ollama (generate) at {base} model={model}")
    return OllamaGenerateClient(base, model)
