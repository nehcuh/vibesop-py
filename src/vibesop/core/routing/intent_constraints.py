"""Conservative intent evidence for automatic routing and verb overrides.

These heuristics are admission guards, not a natural-language authorization
parser. Guarded workflows require affirmative evidence; inactive references
are excluded before semantic arbitration. Slash/! invocation and configured bindings have
their own explicit contracts.
"""

from __future__ import annotations

import re
from typing import Any

_QUOTED = re.compile(
    r'```[\s\S]*?```|`[^`\n]*`|"[^"\n]*"|“[^”\n]*”|「[^」\n]*」|‘[^’\n]*’|(?<!\w)\x27[^\x27\n]*\x27(?!\w)'
)
_NEGATED = re.compile(
    r"\b(?:do not|don['’]?t|never|not|without|no need to|no|avoid)\b|不要|不用|不必|不做|不得|禁止|别用|别执行|别运行",
    re.IGNORECASE,
)
_REFERENCE = re.compile(
    r"\b(?:explain|describe|translate|meaning|tell me about|what (?:is|does|happens|about)|how (?:does|would)|why|said|says)\b|解释|介绍|翻译|含义|是什么|提到|故事",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(?:use|using|run|execute|start|apply|switch|try|do|build|implement|kick off|launch|begin|initiate|invoke|employ|go with)\b|使用|采用|执行|运行|启动|切换|用|进行|走|跑",
    re.IGNORECASE,
)


def intent_clauses(query: str, *, include_references: bool = False) -> list[str]:
    """Unquoted, affirmative clauses; apostrophes in contractions are retained."""

    def unquote_argument(match: re.Match[str]) -> str:
        # Formatting a single skill identifier after an affirmative command
        # differs from quoting a whole command as material for discussion.
        atom = match.group().strip("`\"“”「」‘’'")
        prefix = re.split(
            r"[\n;；。!?！？,，]|\b(?:but|instead|then)\b|而是|然后|接着",
            query[: match.start()],
            flags=re.IGNORECASE,
        )[-1]
        if (
            re.fullmatch(r"[a-zA-Z][\w/:-]*", atom)
            and re.search(
                r"(?:\b(?:use|using|run|execute|try|apply)|使用|采用|用)\s*$", prefix, re.IGNORECASE
            )
            and not (_NEGATED.search(prefix) or _REFERENCE.search(prefix))
        ):
            return atom
        return " "

    text = _QUOTED.sub(unquote_argument, query)
    clauses: list[str] = []
    for raw in re.split(
        r"[\n;；。!?！？,，]|\b(?:but|instead|then)\b|而是|然后|接着", text, flags=re.IGNORECASE
    ):
        # A report about another actor's future actions is not an invocation.
        if re.search(
            r"^(?!(?:i|we|you|please|lets)\b)[\w]+(?:\s+[\w]+){0,3}\s+(?:will|would|is going to|is|are|(?:plans?|intends?|wants?|decided) to)\s+(?:use|using|run|execute)\b|^(?:他|她|他们|工人|对方|.+的工人).{0,12}(?:使用|运行|执行)",
            raw.strip(),
            re.IGNORECASE,
        ):
            continue
        # Only retain evidence BEFORE a negative/reference span. A scope
        # qualifier after an invocation ("use riper without changing APIs")
        # cannot revoke the earlier affirmative request. A name after
        # "do not use" or "explain" supplies no execution evidence.
        barriers = [
            match
            for rx in ((_NEGATED,) if include_references else (_NEGATED, _REFERENCE))
            if (match := rx.search(raw))
        ]
        barrier = min(barriers, key=lambda match: match.start()) if barriers else None
        clause = raw[: barrier.start()] if barrier else raw
        if clause.strip():
            clauses.append(clause.strip())
    return clauses


def phrase_present(text: str, phrase: str) -> bool:
    """Literal phrases with word boundaries for Latin skill identifiers."""
    phrase = phrase.lower().strip()
    if not phrase:
        return False
    pattern = re.escape(phrase)
    if phrase[0].isascii() and phrase[-1].isascii():
        pattern = rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])"
    return re.search(pattern, text.lower()) is not None


def candidate_scope_allows(query: str, candidate: dict[str, Any]) -> bool:
    """Enforce declared prerequisites and reject exclusively inactive mentions.

    This is a necessary-condition check, not a final semantic match. Descriptions
    and intent remain available to the triage adjudicator for richer limits.
    """
    clauses = intent_clauses(query)
    requirements = candidate.get("routing_requires_any") or []
    if requirements and not any(
        phrase_present(clause, str(term)) for clause in clauses for term in requirements
    ):
        return False
    identities = [
        str(candidate.get("id", "")).rsplit("/", maxsplit=1)[-1],
        str(candidate.get("name", "")),
    ]
    names = [p for p in identities if len(p) >= 3 and phrase_present(query, p)]
    if names and not any(phrase_present(clause, p) for clause in clauses for p in names):
        return False
    # Diagnostic/explanatory requests may legitimately match ordinary skills'
    # triggers ("why is this broken"). Only references to their identity require
    # invocation intent; quoted/negated triggers remain inactive everywhere.
    trigger_mentions = [
        str(t) for t in candidate.get("triggers", []) if t and phrase_present(query, str(t))
    ]
    evidence = intent_clauses(query, include_references=True)
    return not trigger_mentions or any(
        phrase_present(clause, p) for clause in evidence for p in trigger_mentions
    )


def workflow_requested(query: str, triggers: list[str], tokens: tuple[str, ...]) -> bool:
    """Require an affirmative action or a standalone declared workflow phrase."""
    for clause in intent_clauses(query):
        normalized = clause.lower().replace("'", "").replace("’", "")
        hits = [t.lower().replace("'", "").replace("’", "") for t in triggers if t]
        named = any(re.search(rf"\b{re.escape(token)}\b", normalized) for token in tokens)
        if (any(t in normalized for t in hits) or named) and (
            _ACTION.search(clause) or normalized in hits or normalized in tokens
        ):
            return True
    return False


def session_end_requested(query: str, triggers: list[str]) -> bool:
    """Require a user exit signal, rather than a trigger in third-person prose."""
    prefix = re.compile(
        r"^(?:(?:我(?:们)?|那|好了|好|嗯|今天|现在|先|就|可以|请|麻烦|准备|打算|要|已经|本次|这次)|\s|(?:ok(?:ay)?|well|please|then|all right|im|i|we)\b)*$",
        re.IGNORECASE,
    )
    for clause in intent_clauses(query):
        normalized = clause.lower().replace("'", "").replace("’", "")
        for trigger in triggers:
            signal = trigger.lower().replace("'", "").replace("’", "")
            start = normalized.find(signal) if signal else -1
            suffix = normalized[start + len(signal) :].strip() if start >= 0 else ""
            ending = re.fullmatch(
                r"(?:(?:了|啦|吧|咯|呀|哈|哦|先|今天|现在)|\s|(?:please|now|here|soon|with this|for today|for now)\b)*",
                suffix,
                re.IGNORECASE,
            )
            question = re.search(rf"{re.escape(trigger)}(?:了|啦|吧)?[?？]", query, re.IGNORECASE)
            if start >= 0 and prefix.fullmatch(normalized[:start]) and ending and not question:
                return True
    return False
