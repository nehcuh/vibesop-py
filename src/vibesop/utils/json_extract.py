"""Extract the first balanced JSON object from LLM text output.

LLMs routinely wrap JSON in markdown fences or surround it with prose. A
naive ``\\{[^{}]*\\}`` regex cannot match objects that themselves contain
nested objects or arrays-of-objects — the character class ``[^{}]`` rejects
any inner brace, so it returns the first inner ``{...}`` instead of the
whole object (silently corrupting downstream parsing). This helper tracks
brace depth to find the matching close, preferring a ```json fence when
present.
"""

from __future__ import annotations

import re

# Matches a ```json (or bare ```) fence and captures the JSON inside.
# Non-greedy .* with re.DOTALL stops at the closing fence.
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?)\s*```", re.DOTALL)


def extract_first_json_object(content: str) -> str | None:
    """Return the first balanced ``{...}`` JSON object found in *content*.

    Preference order:
    1. A ```` ```json ... ``` ```` markdown fence (captures its contents).
    2. The first ``{`` tracked by brace depth to its matching ``}`` — this
       correctly spans nested objects/arrays that a ``[^{}]`` regex would
       truncate.

    Returns ``None`` if no balanced object is found. The result is **not**
    validated as JSON — callers should ``json.loads`` it and handle parse
    errors.
    """
    fence_match = _CODE_FENCE_RE.search(content)
    if fence_match:
        return fence_match.group(1)

    start = content.find("{")
    if start == -1:
        return None

    # Walk braces with string awareness: a `{`/`}` inside a JSON string
    # literal must NOT affect depth. Without this, `{"name": "}"}` truncates
    # at the inner `}` (the depth tracker sees it and returns early). Track
    # in-string state and honour backslash escapes.
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(content[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return None
