"""Maps stool class + color percentages to a human-readable remark + severity."""

from typing import Dict, Optional, Tuple

# Tunable thresholds (percent of crop pixels)
# Raise red thresholds to reduce false-positive blood detections
# (require a larger red fraction before marking as critical).
RED_CRITICAL   = 25.0
RED_SAFE_BELOW = 10.0
GREEN_WARNING  = 15.0
YELLOW_WARNING = 20.0
BROWN_NORMAL   = 50.0


def evaluate(
    pcts: Dict[str, float],
    kind: Optional[str] = "Soft",
) -> Tuple[str, str]:
    """Return (remark, severity). severity in {'normal', 'warning', 'critical'}.

    kind: detected stool class — 'Soft', 'Hard', or 'Watery'.
    Blood (red_pct) overrides stool type and triggers critical regardless.
    """
    red    = pcts.get("red",    0.0)
    green  = pcts.get("green",  0.0)
    yellow = pcts.get("yellow", 0.0)
    brown  = pcts.get("brown",  0.0)

    # Blood always overrides stool type
    if red >= RED_CRITICAL:
        return ("Possible blood detected — consult a vet.", "critical")

    if kind == "Watery":
        if red >= RED_SAFE_BELOW:
            return ("Watery stool with traces of blood — consult a vet.", "critical")
        return ("Watery stool detected — possible diarrhea or GI upset.", "warning")

    if kind == "Hard":
        if red >= RED_SAFE_BELOW:
            return ("Hard stool with traces of blood — consult a vet.", "critical")
        return ("Hard stool detected — possible constipation or dehydration.", "warning")

    # Soft stool — apply color analysis for finer grading
    if green >= GREEN_WARNING:
        return ("Soft stool with unusual pigment — monitor closely.", "warning")
    if yellow >= YELLOW_WARNING:
        return ("Soft yellowish stool — possible diet issue.", "warning")
    if brown >= BROWN_NORMAL and red < RED_SAFE_BELOW:
        return ("Soft stool — looks healthy.", "normal")

    return ("Soft stool — monitor for changes.", "warning")
