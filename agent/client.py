import json
import time

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

        max_retries = 3
        data = None

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                break
            except requests.exceptions.SSLError as exc:
                if attempt >= max_retries:
                    self.logger.exception("request_failed=%s", exc)
                    raise
                wait_seconds = 2 ** (attempt + 1)
                self.logger.warning(
                    "request_retry attempt=%s reason=ssl_error wait_seconds=%s error=%s",
                    attempt + 1,
                    wait_seconds,
                    exc,
                )
                time.sleep(wait_seconds)
            except requests.RequestException as exc:
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None)
                if response is not None:
                    body = response.text[:2000]
                    self.logger.error("request_error_body=%s", body)

                if status_code == 429 and attempt < max_retries:
                    wait_seconds = 2 ** (attempt + 1)
                    self.logger.warning(
                        "request_retry attempt=%s reason=http_429 wait_seconds=%s",
                        attempt + 1,
                        wait_seconds,
                    )
                    time.sleep(wait_seconds)
                    continue

                self.logger.exception("request_failed=%s", exc)
                raise

        if data is None:
            raise RuntimeError("request_failed_without_response_data")

        usage = data.get("usage", {})
        self.logger.info(
            "response status=200 model=%s finish_reason=%s total_tokens=%s %s",
            data.get("model"),
            data.get("choices", [{}])[0].get("finish_reason"),
            usage.get("total_tokens"),
            self._response_brief(data),
        )
        return data
