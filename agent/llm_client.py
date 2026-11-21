"""Single-attempt OpenAI-compatible transport. Retries belong to the Answer Node."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    token_usage: dict[str, int] | None = None


class CompletionError(Exception):
    def __init__(self, message: str, *, retryable: bool = False,
                 model: str | None = None, token_usage: dict[str, int] | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.model = model
        self.token_usage = token_usage


class CompletionClient(Protocol):
    def complete(self, *, messages: list[dict], model: str) -> Completion: ...


class ChatCompletionClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.openai.com/v1",
                 timeout: float = 60.0, transport=None):
        if not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def complete(self, *, messages: list[dict], model: str) -> Completion:
        import httpx

        try:
            # httpx does not retry requests by default. Never log headers or bodies.
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                response = client.post(
                    self.base_url + "/chat/completions",
                    headers={"Authorization": "Bearer " + self.api_key},
                    json={"model": model, "messages": messages,
                          "response_format": {"type": "json_object"}, "store": False},
                )
        except httpx.TransportError as exc:
            raise CompletionError("LLM transport failed", retryable=True) from exc
        if response.status_code >= 400:
            raise CompletionError(
                f"LLM HTTP {response.status_code}",
                retryable=response.status_code in {408, 409, 429} or response.status_code >= 500,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise CompletionError("Invalid LLM response") from exc
        actual_model = data.get("model") if isinstance(data, dict) else None
        normalized = None
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            values = [usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")]
            if all(type(v) is int and v >= 0 for v in values):
                normalized = dict(zip(("input_tokens", "output_tokens", "total_tokens"), values))
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete or refused completion")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not isinstance(actual_model, str) or not actual_model:
                raise ValueError("Missing content or model")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise CompletionError("Invalid or incomplete LLM response",
                                  model=actual_model if isinstance(actual_model, str) else None,
                                  token_usage=normalized) from exc
        return Completion(content=content, model=actual_model, token_usage=normalized)
