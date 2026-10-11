import httpx


class OllamaClient:
    """Server-side Ollama Cloud transport shared by agent workflows."""
    def __init__(self, settings):
        self.settings = settings
        self.usage = []

    def chat(self, messages, tools=None):
        body = {"model": self.settings.ollama_model, "messages": messages, "stream": False,
                "options": {"temperature": self.settings.ollama_temperature}}
        if tools:
            body["tools"] = tools
        key = self.settings.ollama_api_key.get_secret_value()
        with httpx.Client(base_url=self.settings.ollama_base_url, timeout=self.settings.ollama_timeout_seconds) as client:
            response = client.post("/api/chat", json=body, headers={"Authorization": f"Bearer {key}"})
            response.raise_for_status()
            result = response.json()
            self.usage.append({"model": result.get("model", self.settings.ollama_model),
                               "input_tokens": result.get("prompt_eval_count"),
                               "output_tokens": result.get("eval_count")})
            return result
