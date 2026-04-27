def compute_ambiguity(
    intent: float,
    outcome: float,
    scope: float,
    constraints: float,
    success: float,
) -> float:
    """Compute ambiguity score from 5-dimension clarity assessment.

    Each dimension is scored 0.0-1.0 (0 = no clarity, 1 = fully clear).
    Returns ambiguity from 0.0 (fully clear) to 1.0 (totally ambiguous).

    Formula from OMX deep-interview skill:
        ambiguity = 1.0 - (intent×0.30 + outcome×0.25 + scope×0.20
                           + constraints×0.15 + success×0.10)
    """
    clarity = (
        intent * 0.30
        + outcome * 0.25
        + scope * 0.20
        + constraints * 0.15
        + success * 0.10
    )
    return max(0.0, min(1.0, 1.0 - clarity))
