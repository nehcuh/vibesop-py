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

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from vibesop.llm import create_from_env
from vibesop.core.session_analyzer import SkillSuggestion


@dataclass
class EnhancedSkill:
    """AI-enhanced skill suggestion.

    Attributes:
        name: Improved skill name
        description: Enhanced description
        category: Skill category
        tags: Relevant tags
        trigger_conditions: Clear trigger conditions
        steps: Suggested steps
        original: Original suggestion
    """

    name: str
    description: str
    category: str
    tags: list[str]
    trigger_conditions: list[str]
    steps: list[str]
    original: SkillSuggestion
    confidence: float = 0.0


class AIEnhancer:
    """Enhance skill suggestions using AI.

    Example:
        >>> enhancer = AIEnhancer()
        >>> enhanced = enhancer.enhance_suggestion(suggestion)
        >>> print(enhanced.name)  # Better name
        >>> print(enhanced.description)  # Professional description
    """

    def __init__(self) -> None:
        """Initialize the AI enhancer."""
        self._llm = create_from_env()

    def enhance_suggestion(
        self,
        suggestion: SkillSuggestion,
    ) -> EnhancedSkill:
        """Enhance a skill suggestion using AI.

        Args:
            suggestion: Original skill suggestion

        Returns:
            Enhanced skill with better name, description, etc.
        """
        # Generate enhancement prompt
        prompt = self._build_enhancement_prompt(suggestion)

        # Call LLM
        response = self._llm.complete(
            prompt,
            max_tokens=500,
            temperature=0.3,  # Lower temperature for consistency
        )

        # Parse response
        enhanced = self._parse_enhancement(response, suggestion)

        return enhanced

    def enhance_batch(
        self,
        suggestions: list[SkillSuggestion],
    ) -> list[EnhancedSkill]:
        """Enhance multiple skill suggestions.

        Args:
            suggestions: List of skill suggestions

        Returns:
            List of enhanced skills
        """
        enhanced_skills = []

        for suggestion in suggestions:
            try:
                enhanced = self.enhance_suggestion(suggestion)
                enhanced_skills.append(enhanced)
            except Exception:
                # If AI enhancement fails, use original
                enhanced_skills.append(self._fallback_enhancement(suggestion))

        return enhanced_skills

    def _build_enhancement_prompt(
        self,
        suggestion: SkillSuggestion,
    ) -> str:
        """Build AI prompt for skill enhancement.

        Args:
            suggestion: Skill suggestion to enhance

        Returns:
            AI prompt
        """
        examples_text = "\n".join(
            f"- {q[:80]}..."
            for q in suggestion.trigger_queries[:5]
        )

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
        """Parse AI response into EnhancedSkill.

        Args:
            response: AI response text
            original: Original suggestion

        Returns:
            Enhanced skill
        """
        import json
        import re

        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response.strip())

            # Validate required fields
            name = data.get("name", original.skill_name)
            description = data.get("description", original.description)
            category = data.get("category", "development")
            tags = data.get("tags", [])
            trigger_conditions = data.get("trigger_conditions", [])
            steps = data.get("steps", [])

            # Calculate confidence based on response quality
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
            # Fallback to simple enhancement
            return self._fallback_enhancement(original)

    def _fallback_enhancement(
        self,
        suggestion: SkillSuggestion,
    ) -> EnhancedSkill:
        """Create a simple enhancement without AI.

        Args:
            suggestion: Original suggestion

        Returns:
            Basic enhanced skill
        """
        # Generate a better name from skill_name
        name = self._improve_name(suggestion.skill_name)

        # Improve description
        description = self._improve_description(suggestion)

        # Detect category from keywords
        category = self._detect_category(suggestion.trigger_queries)

        # Extract tags from queries
        tags = self._extract_tags(suggestion.trigger_queries)

        return EnhancedSkill(
            name=name,
            description=description,
            category=category,
            tags=tags,
            trigger_conditions=[f"User asks about: {suggestion.trigger_queries[0][:50]}"],
            steps=[
                "Understand the user's request",
                "Analyze the context",
                "Provide appropriate assistance",
            ],
            original=suggestion,
            confidence=0.5,
        )

    def _improve_name(self, original_name: str) -> str:
        """Improve skill name.

        Args:
            original_name: Original skill name

        Returns:
            Improved name
        """
        # Remove common prefixes
        name = original_name
        for prefix in ["请帮我", "帮我", "请", "我想要"]:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
                break

        # Capitalize first letter
        if name and name[0].islower():
            name = name[0].upper() + name[1:]

        return name

    def _improve_description(self, suggestion: SkillSuggestion) -> str:
        """Improve skill description.

        Args:
            suggestion: Skill suggestion

        Returns:
            Improved description
        """
        if not suggestion.description.startswith(("Handle", "Help", "Assist")):
            return suggestion.description

        # Generate better description
        first_query = suggestion.trigger_queries[0] if suggestion.trigger_queries else ""
        action = self._extract_action(first_query)

        return f"{action} user requests related to: {first_query[:50]}..."

    def _extract_action(self, query: str) -> str:
        """Extract action verb from query.

        Args:
            query: User query

        Returns:
            Action verb
        """
        action_keywords = {
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
        """Detect skill category from queries.

        Args:
            queries: Example queries

        Returns:
            Category name
        """
        category_keywords = {
            "development": ["创建", "实现", "编写", "develop", "create", "implement", "write"],
            "testing": ["测试", "test", "verify", "check"],
            "debugging": ["调试", "修复", "bug", "debug", "fix", "error"],
            "review": ["审查", "检查", "review", "check", "inspect"],
            "documentation": ["文档", "说明", "document", "explain", "readme"],
            "deployment": ["部署", "发布", "deploy", "release", "publish"],
            "security": ["安全", "漏洞", "security", "vulnerability", "scan"],
            "optimization": ["优化", "性能", "optimize", "performance", "improve"],
        }

        # Score each category
        category_scores = {cat: 0 for cat in category_keywords}

        for query in queries:
            query_lower = query.lower()
            for category, keywords in category_keywords.items():
                for keyword in keywords:
                    if keyword in query_lower:
                        category_scores[category] += 1

        # Return highest scoring category
        best_category = max(category_scores, key=category_scores.get)

        return best_category if category_scores[best_category] > 0 else "development"

    def _extract_tags(self, queries: list[str]) -> list[str]:
        """Extract relevant tags from queries.

        Args:
            queries: Example queries

        Returns:
            List of tags
        """
        import re

        # Extract potential tags (capitalized words, technical terms)
        tags = set()

        for query in queries:
            # Extract capitalized words
            words = re.findall(r'\b[A-Z][a-z]+\b', query)
            tags.update(words[:3])  # Take first 3

            # Extract technical terms (words with numbers, common tech patterns)
            tech_terms = re.findall(r'\b\w+(?:\.js|\.py|\.md|API|SQL|HTTP)\b', query)
            tags.update(tech_terms)

        return sorted(list(tags))[:5]  # Top 5 tags

    def _calculate_confidence(self, data: dict) -> float:
        """Calculate confidence score for AI enhancement.

        Args:
            data: Parsed AI response

        Returns:
            Confidence score [0, 1]
        """
        score = 0.0

        # Check for required fields
        if data.get("name") and len(data["name"]) > 3:
            score += 0.2

        if data.get("description") and len(data["description"]) > 20:
            score += 0.2

        if data.get("category") in ["development", "testing", "debugging", "review",
                                  "documentation", "deployment", "security", "optimization"]:
            score += 0.2

        if data.get("tags") and len(data["tags"]) >= 3:
            score += 0.2

        if data.get("trigger_conditions") and len(data["trigger_conditions"]) >= 2:
            score += 0.1

        if data.get("steps") and len(data["steps"]) >= 3:
            score += 0.1

        return min(score, 1.0)
