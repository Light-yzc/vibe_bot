import json

import requests


class ArkClient:
    def __init__(self, api_url: str, api_key: str, model: str, logger):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.logger = logger

    def _compact_log_value(self, value, limit: int = 180):
        try:
            if isinstance(value, str):
                text = value
            else:
                text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            text = str(value)

        text = text.replace("\n", "\\n").replace("\r", "")
        if len(text) > limit:
            return f"{text[: limit - 3]}..."
        return text

    def _response_brief(self, data):
        message = ((data.get("choices") or [{}])[0]).get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            names = [call.get("function", {}).get("name", "unknown") for call in tool_calls]
            return f"tools={self._compact_log_value(names, limit=120)}"

        content = message.get("content") or ""
        if content:
            return f"content={self._compact_log_value(content, limit=120)}"
        return "content=[empty]"

    def chat(self, messages, tools=None, tool_choice="auto"):
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        self.logger.info("request model=%s messages=%s tools=%s tool_choice=%s", self.model, len(messages), bool(tools), tool_choice)

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            response = getattr(exc, "response", None)
            if response is not None:
                body = response.text[:2000]
                self.logger.error("request_error_body=%s", body)
            self.logger.exception("request_failed=%s", exc)
            raise

        usage = data.get("usage", {})
        self.logger.info(
            "response status=200 model=%s finish_reason=%s total_tokens=%s %s",
            data.get("model"),
            data.get("choices", [{}])[0].get("finish_reason"),
            usage.get("total_tokens"),
            self._response_brief(data),
        )
        return data
