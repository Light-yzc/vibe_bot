import json
import os
from pathlib import Path

import requests


URL = "https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions"
API_KEY = os.getenv("ARK_API_KEY", "").strip()
MODEL = os.getenv("ARK_MODEL", "kimi-k2.5").strip() or "kimi-k2.5"
SKILL_PATH = Path(__file__).with_name("skill.md")


def parse_skills() -> dict:
    text = SKILL_PATH.read_text(encoding="utf-8")
    sections = text.split("\n## ")
    skills = {}

    for index, section in enumerate(sections):
        if index == 0:
            continue

        lines = section.strip().splitlines()
        skill_id = lines[0].strip()
        description = ""
        body_start = 1

        for i, line in enumerate(lines[1:], start=1):
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
                body_start = i + 1
                break

        skills[skill_id] = {
            "id": skill_id,
            "description": description,
            "content": "\n".join(lines[body_start:]).strip(),
        }

    return skills


SKILLS = parse_skills()


def build_skill_catalog() -> str:
    lines = ["Available skills:"]
    for skill in SKILLS.values():
        lines.append(f'- {skill["id"]}: {skill["description"]}')
    return "\n".join(lines)


def load_skill(skill_id: str) -> dict:
    skill = SKILLS.get(skill_id)
    if not skill:
        return {"error": f"unknown skill: {skill_id}"}
    return {
        "id": skill["id"],
        "description": skill["description"],
        "content": skill["content"],
    }


def chat(messages, tools=None):
    if not API_KEY:
        raise RuntimeError("Missing ARK_API_KEY. Export it before running test_ark.py")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    payload = {
        "model": MODEL,
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    response = requests.post(URL, headers=headers, json=payload, timeout=60)
    print("status:", response.status_code)
    data = response.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def run_tool(tool_call: dict):
    name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])

    if name == "load_skill":
        return load_skill(arguments["skill_id"])
    return {"error": f"unknown tool: {name}"}


def main():
    skill_catalog = build_skill_catalog()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "load_skill",
                "description": "Load the full content of a skill only when its summary looks relevant.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_id": {
                            "type": "string",
                            "description": "Skill id from the catalog, such as lazy_skill_loading or tool_use_loop.",
                        }
                    },
                    "required": ["skill_id"],
                },
            },
        },
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are testing lazy skill loading. The skill catalog below contains only ids and one-line summaries. "
                "Do not ask for the full skill file immediately. Only call load_skill when one summary appears directly relevant to the user's request. "
                "After reading the loaded skill, answer briefly in Chinese and mention which skill was used.\n\n"
                f"{skill_catalog}"
            ),
        },
        {
            "role": "user",
            "content": (
                "我想做一个像 OpenCode / Claude Code 那样的 skill.md 机制：默认不把整个文件发给模型，"
                "而是先给描述，需要时再加载全文。请先决定要不要看 skill catalog，"
                "如果需要再加载合适的 skill，然后告诉我应该怎么实现。"
            ),
        },
    ]

    while True:
        response = chat(messages, tools=tools)
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            break

        messages.append(message)

        for tool_call in tool_calls:
            result = run_tool(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    print("\n--- final answer ---")
    print(message["content"])


if __name__ == "__main__":
    main()
