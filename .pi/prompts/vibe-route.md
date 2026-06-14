---
description: Route a user request to the appropriate VibeSOP skill
argument-hint: "<user_request>"
---

Run `vibe route "$ARGUMENTS"` to find the best matching skill for this request.

Then read the matched skill file at `skills/<matched-skill>/SKILL.md` and follow its steps exactly.

If no match is found, proceed with the user's request directly.