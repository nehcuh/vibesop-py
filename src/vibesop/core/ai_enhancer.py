"""AI-powered skill enhancement using LLM.

This module uses LLM to improve:
- Skill names (more descriptive)
- Skill descriptions (more professional)
- Trigger conditions (more accurate)
- Skill categorization

Usage:
    enhancer = AIEnhancer()
    enhanced = enhancer.enhance_suggestion(suggestion)
    print(enhanced.name)
    print(enhanced.description)
"""

from dataclasses import dataclass
from typing import Any, cast

from vibesop.core.session_analyzer import SkillSuggestion
from vibesop.llm import create_from_env


@dataclass
class EnhancedSkill:
    name: str
    description: str
    category: str
    tags: list[str]
    trigger_conditions: list[str]
    steps: list[str]
    original: SkillSuggestion
    confidence: float = 0.0


class AIEnhancer:
    def __init__(self) -> None:
        self._llm = create_from_env()

    def enhance_suggestion(
        self,
        suggestion: SkillSuggestion,
    ) -> EnhancedSkill:
        try:
            prompt = self._build_enhancement_prompt(suggestion)

            llm_response = self._llm.call(
                prompt,
                max_tokens=500,
                temperature=0.3,
            )

            enhanced = self._parse_enhancement(llm_response.content, suggestion)

            return enhanced

        except Exception:
            return self._fallback_enhancement(suggestion)

    def enhance_batch(
        self,
        suggestions: list[SkillSuggestion],
    ) -> list[EnhancedSkill]:
        enhanced_skills: list[EnhancedSkill] = []

        for suggestion in suggestions:
            try:
                enhanced = self.enhance_suggestion(suggestion)
                enhanced_skills.append(enhanced)
            except Exception:
                enhanced_skills.append(self._fallback_enhancement(suggestion))

        return enhanced_skills

    def _build_enhancement_prompt(
        self,
        suggestion: SkillSuggestion,
    ) -> str:
        examples_text = "\n".join(f"- {q[:80]}..." for q in suggestion.trigger_queries[:5])

        prompt = f"""You are an expert at creating reusable workflow skills.

Based on the following user query patterns, create a professional skill definition:

## Query Patterns (Frequency: {suggestion.frequency})
{examples_text}

## Your Task

Generate a JSON response with:
{{
  "name": "Short, memorable skill name (2-4 words, title case)",
  "description": "Clear one-sentence description of what this skill does",
  "category": "One of: development, testing, debugging, review, documentation, deployment, security, optimization",
  "tags": ["tag1", "tag2", "tag3"],
  "trigger_conditions": [
    "Condition 1 when this skill should trigger",
    "Condition 2"
  ],
  "steps": [
    "Step 1: What to do first",
    "Step 2: What to do next",
    "Step 3: Final step"
  ]
}}

## Guidelines

- Name should be actionable (e.g., "Code Performance Optimization" not "Performance")
- Description should start with a verb (e.g., "Optimize", "Review", "Test")
- Category should match the most common pattern
- Tags should include relevant technologies and concepts
- Trigger conditions should be specific and checkable
- Steps should be clear and actionable

Return ONLY the JSON, no other text.
"""

        return prompt

    def _parse_enhancement(
        self,
        response: str,
        original: SkillSuggestion,
    ) -> EnhancedSkill:
        import json
        import re

        try:
            json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
            if json_match:
                data: dict[str, Any] = json.loads(json_match.group())
            else:
                data = json.loads(response.strip())

            name = str(data.get("name", original.skill_name))
            description = str(data.get("description", original.description))
            category = str(data.get("category", "development"))
            tags: list[Any] = list(data.get("tags", []) or [])
            trigger_conditions: list[Any] = list(data.get("trigger_conditions", []) or [])
            steps: list[Any] = list(data.get("steps", []) or [])

            confidence = self._calculate_confidence(data)

            return EnhancedSkill(
                name=name,
                description=description,
                category=category,
                tags=tags,
                trigger_conditions=trigger_conditions,
                steps=steps,
                original=original,
                confidence=confidence,
            )

        except Exception:
            return self._fallback_enhancement(original)

    def _fallback_enhancement(
        self,
        suggestion: SkillSuggestion,
    ) -> EnhancedSkill:
        name = self._improve_name(suggestion.skill_name)

        description = self._improve_description(suggestion)

        category = self._detect_category(suggestion.trigger_queries)

        tags = self._extract_tags(suggestion.trigger_queries)

        if suggestion.trigger_queries:
            trigger_conditions = [f"User asks about: {suggestion.trigger_queries[0][:50]}"]
        else:
            trigger_conditions = ["User requests assistance"]

        return EnhancedSkill(
            name=name,
            description=description,
            category=category,
            tags=tags,
            trigger_conditions=trigger_conditions,
            steps=[
                "Understand the user's request",
                "Analyze the context",
                "Provide appropriate assistance",
            ],
            original=suggestion,
            confidence=0.5,
        )

    def _improve_name(self, original_name: str) -> str:
        name = original_name
        for prefix in ["请帮我", "帮我", "请", "我想要"]:
            if name.startswith(prefix):
                name = name[len(prefix) :].strip()
                break

        if name and name[0].islower():
            name = name[0].upper() + name[1:]

        return name

    def _improve_description(self, suggestion: SkillSuggestion) -> str:
        if not suggestion.description.startswith(("Handle", "Help", "Assist")):
            return suggestion.description

        first_query = suggestion.trigger_queries[0] if suggestion.trigger_queries else ""
        action = self._extract_action(first_query)

        return f"{action} user requests related to: {first_query[:50]}..."

    def _extract_action(self, query: str) -> str:
        action_keywords: dict[str, str] = {
            "优化": "Optimize",
            "检查": "Check",
            "测试": "Test",
            "审查": "Review",
            "部署": "Deploy",
            "修复": "Fix",
            "调试": "Debug",
            "创建": "Create",
            "重构": "Refactor",
            "optimize": "Optimize",
            "check": "Check",
            "test": "Test",
            "review": "Review",
            "deploy": "Deploy",
            "fix": "Fix",
            "debug": "Debug",
            "create": "Create",
            "refactor": "Refactor",
        }

        query_lower = query.lower()
        for keyword, action in action_keywords.items():
            if keyword in query_lower:
                return action

        return "Assist"

    def _detect_category(self, queries: list[str]) -> str:
        category_keywords: dict[str, list[str]] = {
            "development": ["创建", "实现", "编写", "develop", "create", "implement", "write"],
            "testing": ["测试", "test", "verify", "check"],
            "debugging": ["调试", "修复", "bug", "debug", "fix", "error"],
            "review": ["审查", "检查", "review", "check", "inspect"],
            "documentation": ["文档", "说明", "document", "explain", "readme"],
            "deployment": ["部署", "发布", "deploy", "release", "publish"],
            "security": ["安全", "漏洞", "security", "vulnerability", "scan"],
            "optimization": ["优化", "性能", "optimize", "performance", "improve"],
        }

        category_scores: dict[str, int] = dict.fromkeys(category_keywords, 0)

        for query in queries:
            query_lower = query.lower()
            for category, keywords in category_keywords.items():
                for keyword in keywords:
                    if keyword in query_lower:
                        category_scores[category] += 1

        best_category = max(category_scores, key=lambda k: category_scores[k])

        return best_category if category_scores[best_category] > 0 else "development"

    def _extract_tags(self, queries: list[str]) -> list[str]:
        import re

        tags: set[str] = set()

        for query in queries:
            words = re.findall(r"\b[A-Z][a-z]+\b", query)
            tags.update(words[:3])

            tech_terms = re.findall(r"\b\w+(?:\.js|\.py|\.md|API|SQL|HTTP)\b", query)
            tags.update(tech_terms)

        return sorted(tags)[:5]

    def _calculate_confidence(self, data: dict[str, Any]) -> float:
        score = 0.0

        name_val = data.get("name")
        if name_val and isinstance(name_val, str) and len(name_val) > 3:
            score += 0.2

        desc_val = data.get("description")
        if desc_val and isinstance(desc_val, str) and len(desc_val) > 20:
            score += 0.2

        cat_val = data.get("category")
        if cat_val in [
            "development",
            "testing",
            "debugging",
            "review",
            "documentation",
            "deployment",
            "security",
            "optimization",
        ]:
            score += 0.2

        tags_val = data.get("tags")
        if isinstance(tags_val, list):
            tags_list = cast("list[Any]", tags_val)
            if len(tags_list) >= 3:
                score += 0.2

        tc_val = data.get("trigger_conditions")
        if isinstance(tc_val, list):
            tc_list = cast("list[Any]", tc_val)
            if len(tc_list) >= 2:
                score += 0.1

        steps_val = data.get("steps")
        if isinstance(steps_val, list):
            steps_list = cast("list[Any]", steps_val)
            if len(steps_list) >= 3:
                score += 0.1

        return min(score, 1.0)
