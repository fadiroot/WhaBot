"""Fallback when the LLM ignores OpenAI `tools=` (common with Ollama / small models).

The model must reply with exactly one JSON object per turn:
  {"tool":"<name>","args":{...}}

Also accepts legacy hallucination shapes:
  {"name":"<name>","parameters":{...}}
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agents.tools import TOOL_DISPATCH

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def tool_names_line() -> str:
    return ", ".join(sorted(TOOL_DISPATCH.keys()))


JSON_TOOL_INSTRUCTION = f"""

---
TOOL PROTOCOL (required — local models often ignore OpenAI function calling):
Respond with **exactly one** JSON object and **nothing else** (no markdown, no prose before/after).

Shape: {{"tool":"<name>","args":{{...}}}}

Valid tool names: {tool_names_line()}

To send the user a final reply, use only:
{{"tool":"finish","args":{{"message":"your short WhatsApp-friendly summary"}}}}

Example: {{"tool":"search_code","args":{{"query":"authentication middleware","k":8}}}}
For GitHub PR questions use: {{"tool":"summarize_pull_request","args":{{"number":1}}}}
"""


def _first_balanced_braces(text: str) -> Optional[str]:
    """Return first `{ ... }` slice by brace counting (tool JSON is usually one object)."""
    start = text.find("{")
    while start >= 0:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        start = text.find("{", start + 1)
    return None


def _lenient_json_loads(raw: str) -> Any:
    """Parse JSON; fix common LLM mistakes like unquoted keys (`k:10` instead of `"k":10`)."""
    s = raw.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r"([\{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', s)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


def parse_tool_json_response(content: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Return (tool_name, args) or None if no usable tool JSON found."""
    if not content or not content.strip():
        return None
    text = content.strip()

    candidates: List[str] = []
    m = _JSON_FENCE.search(text)
    if m:
        candidates.append(m.group(1).strip())
    candidates.append(text)

    for blob in candidates:
        chunk = _first_balanced_braces(blob)
        if not chunk:
            continue
        obj = _lenient_json_loads(chunk)
        if obj is None:
            continue
        if isinstance(obj, list) and obj:
            obj = obj[0]
        if not isinstance(obj, dict):
            continue

        name: Optional[str] = None
        args: Dict[str, Any] = {}

        if "tool" in obj:
            name = str(obj["tool"]).strip()
            raw = obj.get("args")
            args = raw if isinstance(raw, dict) else {}
        elif "name" in obj:
            name = str(obj["name"]).strip()
            for key in ("parameters", "arguments", "args"):
                raw = obj.get(key)
                if isinstance(raw, dict):
                    args = raw
                    break

        if not name:
            continue
        return name, args

    return None
