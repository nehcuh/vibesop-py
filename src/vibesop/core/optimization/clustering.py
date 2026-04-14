"""Semantic clustering of skills by intent similarity."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class SkillClusterIndex:
    """Automatically cluster skills by intent similarity."""

    def __init__(self):
        self._clusters: dict[str, list[str]] = {}
        self._skill_to_cluster: dict[str, str] = {}
        self._cluster_intents: dict[str, list[str]] = {}
        self._built = False

    def build(self, skills: list[dict[str, Any]]) -> dict[str, list[str]]:
        if len(skills) < 2:
            self._clusters = {"default": [s["id"] for s in skills]} if skills else {}
            self._skill_to_cluster = {s["id"]: "default" for s in skills}
            self._built = True
            return self._clusters
        if len(skills) < 10:
            return self._cluster_by_intent(skills)
        return self._cluster_by_tfidf(skills)

    def _cluster_by_intent(self, skills: list[dict[str, Any]]) -> dict[str, list[str]]:
        clusters: dict[str, list[str]] = defaultdict(list)
        for skill in skills:
            intent = skill.get("intent", "other").lower().strip()
            cluster_name = self._normalize_intent(intent)
            clusters[cluster_name].append(skill["id"])
        self._clusters = dict(clusters)
        self._skill_to_cluster = {
            skill_id: cluster_id
            for cluster_id, skill_ids in self._clusters.items()
            for skill_id in skill_ids
        }
        self._built = True
        return self._clusters

    def _cluster_by_tfidf(self, skills: list[dict[str, Any]]) -> dict[str, list[str]]:
        try:
            import numpy as np
            from sklearn.cluster import KMeans

            from vibesop.core.matching.tfidf import TFIDFCalculator
            from vibesop.core.matching.tokenizers import tokenize

            tfidf = TFIDFCalculator()
            documents = []
            for skill in skills:
                text = f"{skill.get('description', '')} {skill.get('intent', '')}"
                documents.append(tokenize(text))
            tfidf.fit(documents)

            vectors = []
            for doc in documents:
                vec = tfidf.transform(doc)
                vectors.append(vec.to_dict())

            vocabulary = tfidf.get_vocabulary()
            vector_array = np.array([[v.get(term, 0.0) for term in vocabulary] for v in vectors])

            best_k = 3
            best_score = -1
            for k in range(2, min(8, len(skills))):
                km = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = km.fit_predict(vector_array)
                try:
                    from sklearn.metrics import silhouette_score

                    score = float(silhouette_score(vector_array, labels))
                except ImportError:
                    score = 0.0
                if score > best_score:
                    best_score = score
                    best_k = k

            km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
            labels = km.fit_predict(vector_array)

            clusters: dict[str, list[str]] = defaultdict(list)
            for i, label in enumerate(labels):
                cluster_name = f"cluster_{label}"
                clusters[cluster_name].append(skills[i]["id"])

            self._clusters = dict(clusters)
        except ImportError:
            return self._cluster_by_intent(skills)

        self._skill_to_cluster = {
            skill_id: cluster_id
            for cluster_id, skill_ids in self._clusters.items()
            for skill_id in skill_ids
        }
        self._built = True
        return self._clusters

    def _normalize_intent(self, intent: str) -> str:
        intent = intent.lower().strip()
        intent_map = {
            "debug": "debugging",
            "debugging": "debugging",
            "root cause": "debugging",
            "investigate": "debugging",
            "plan": "planning",
            "planning": "planning",
            "design": "planning",
            "execute": "execution",
            "execution": "execution",
            "workflow": "execution",
            "test": "testing",
            "testing": "testing",
            "qa": "testing",
            "quality": "testing",
            "ship": "shipping",
            "release": "shipping",
            "deploy": "shipping",
            "brainstorm": "brainstorming",
            "product": "product_thinking",
            "review": "review",
            "refactor": "refactoring",
            "architecture": "architecture",
            "session": "session_management",
            "verification": "verification",
            "experiment": "experimentation",
            "requirements": "requirements",
            "parallel": "parallel_execution",
        }
        for keyword, cluster in intent_map.items():
            if keyword in intent:
                return cluster
        return "other"

    def get_cluster(self, skill_id: str) -> str | None:
        return self._skill_to_cluster.get(skill_id)

    def get_cluster_members(self, cluster_id: str) -> list[str]:
        return self._clusters.get(cluster_id, [])

    def get_relevant_clusters(self, query: str) -> list[str]:
        query_lower = query.lower()
        relevant = []
        for cluster_id, _skill_ids in self._clusters.items():
            cluster_keywords = cluster_id.replace("_", " ").split()
            if any(kw in query_lower for kw in cluster_keywords):
                relevant.append(cluster_id)
                continue
            if hasattr(self, "_cluster_intents"):
                intents = self._cluster_intents.get(cluster_id, [])
                if any(kw in query_lower for kw in intents):
                    relevant.append(cluster_id)
        return relevant

    def resolve_conflicts(
        self,
        _query: str,
        matched_skills: list[str],
        confidences: dict[str, float] | None = None,
        confidence_gap_threshold: float = 0.1,
    ) -> dict[str, Any]:
        if len(matched_skills) <= 1:
            return {
                "primary": matched_skills[0] if matched_skills else None,
                "alternatives": [],
                "needs_review": False,
            }

        cluster_groups: dict[str, list[str]] = defaultdict(list)
        for skill_id in matched_skills:
            cluster = self.get_cluster(skill_id)
            if cluster:
                cluster_groups[cluster].append(skill_id)

        if not cluster_groups:
            sorted_skills = sorted(
                matched_skills, key=lambda s: (confidences or {}).get(s, 0.0), reverse=True
            )
            return {
                "primary": sorted_skills[0],
                "alternatives": sorted_skills[1:],
                "needs_review": False,
            }

        primary = None
        alternatives = []
        needs_review = False

        for _cluster_id, skills_in_cluster in cluster_groups.items():
            sorted_skills = sorted(
                skills_in_cluster, key=lambda s: (confidences or {}).get(s, 0.0), reverse=True
            )
            if primary is None:
                primary = sorted_skills[0]
                alternatives.extend(sorted_skills[1:])
            else:
                alternatives.extend(sorted_skills)
            if len(sorted_skills) >= 2 and confidences:
                top_score = confidences.get(sorted_skills[0], 0.0)
                second_score = confidences.get(sorted_skills[1], 0.0)
                if top_score - second_score < confidence_gap_threshold:
                    needs_review = True

        return {"primary": primary, "alternatives": alternatives, "needs_review": needs_review}
