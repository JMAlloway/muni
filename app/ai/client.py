# app/ai/client.py
import os
import requests

class OllamaClient:
    """
    Minimal Ollama client for our use case.
    Uses /api/chat so we can send system+user.
    Docs: https://docs.ollama.com/api  (or http://localhost:11434/api/chat)
    """
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages, temperature=0, format=None):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        if format:
            payload["format"] = format

        resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # Ollama returns {"message": {"role": "assistant", "content": "..."}, ...}
        return data["message"]["content"]


def get_llm_client():
    provider = os.getenv("AI_PROVIDER", "").lower()
    if provider == "ollama":
        # you can also set OLLAMA_MODEL=llama3.1 or whatever you pulled
        model = os.getenv("OLLAMA_MODEL", "llama3")
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return OllamaClient(base_url=base, model=model)

    if provider == "openai":
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        return OpenAI(api_key=api_key)

    # default: no LLM (rule-based only)
    return None
