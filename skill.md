# Skills Catalog

## python_api_client
description: Build small Python HTTP clients with requests, timeouts, JSON parsing, and clear error handling.

Use this skill when the user wants a Python script that calls an API and prints or parses the response.

### Guidance
- Prefer `requests` for a short demo script.
- Set an explicit timeout.
- Print both status code and parsed JSON when debugging.
- Fall back to raw text if JSON decoding fails.
- Keep the first example minimal, then add retries or exception handling only if needed.

### Example
```python
import json
import requests

resp = requests.post(url, headers=headers, json=payload, timeout=60)
print(resp.status_code)
try:
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
except Exception:
    print(resp.text)
```

## tool_use_loop
description: Implement OpenAI-style tool use by advertising tool schemas, executing tool calls locally, and sending tool results back.

Use this skill when the model should decide whether to call a local function, then continue after the result is returned.

### Guidance
- Send tool metadata in the `tools` field.
- Use `tool_choice: auto` when the model may choose a tool.
- After the model returns `tool_calls`, append the assistant message to `messages`.
- Execute each tool locally.
- Return tool results with role `tool` and the matching `tool_call_id`.
- Make a follow-up completion request to get the final user-facing answer.

### Example
```python
messages.append(message)
messages.append(
    {
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result, ensure_ascii=False),
    }
)
```

## lazy_skill_loading
description: Avoid sending a full skill file up front; expose only summaries first, then load the full section on demand.

Use this skill when you want OpenCode/Claude Code style behavior where the model sees a lightweight catalog and fetches detailed instructions only when needed.

### Guidance
- Keep a catalog of skill ids and one-line descriptions in the initial context.
- Provide a tool like `load_skill(skill_id)` to fetch the full section only when necessary.
- Optionally provide `list_skills()` if the catalog is generated dynamically.
- Ask the model to avoid loading a skill unless the summary suggests it is relevant.
- Once loaded, append the skill content as a tool result rather than re-sending the entire file every turn.

### Example
```text
system: You may inspect the skill catalog. Load a skill only when its summary is relevant.
tool: list_skills() -> [{"id": "lazy_skill_loading", "description": "Avoid sending a full skill file up front..."}]
tool: load_skill("lazy_skill_loading") -> full markdown section
```
