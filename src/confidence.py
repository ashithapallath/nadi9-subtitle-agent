"""
Confidence scoring with an attached *reason* -- the brief is explicit that
"a number alone is not enough." This is deliberately a separate module
from both translator.py and verifier.py so that confidence is computed
from the same inputs the verifier used, not by the translator marking its
own work.
"""
from __future__ import annotations
from .evidence import EvidenceStore
from .translator import DraftTranslation


def compute_confidence(draft: DraftTranslation, store: EvidenceStore, memory=None) -> tuple[float, str]:
    if draft.nadi_9_text is None:
        return 0.0, "No supported translation could be constructed (unsupported vocabulary present)."

    if not draft.evidence:
        return 0.1, "Translation produced but no evidence references were attached -- treat as unsupported."

    reliabilities = []
    for ref in draft.evidence:
        base_ref = ref.split("#")[0]
        item = store.get(base_ref)
        if item:
            reliabilities.append(item.reliability)
    avg_reliability = sum(reliabilities) / len(reliabilities) if reliabilities else 0.3

    score = avg_reliability
    reasons = [f"average source reliability {avg_reliability:.2f} across {len(reliabilities)} evidence item(s)"]

    if draft.conflicts:
        penalty = 0.15 * len(draft.conflicts)
        score -= penalty
        reasons.append(f"-{penalty:.2f} for {len(draft.conflicts)} unresolved conflict(s)")

    disputed_rules_used = []
    if draft.rules_used and memory is not None:
        for rid in draft.rules_used:
            rule = memory.rules.get(rid)
            if rule and rule.status != "supported":
                disputed_rules_used.append(rid)
    if disputed_rules_used:
        # ONLY a disputed/candidate rule caps confidence -- a well-supported rule
        # (e.g. negation-1) contributing to a translation is not itself a reason
        # for suspicion.
        score = min(score, 0.55)
        reasons.append(f"capped at 0.55: derivation relies on disputed rule(s) {disputed_rules_used}")

    if len(draft.evidence) >= 2 and not draft.conflicts:
        score += 0.05
        reasons.append("+0.05 for multiple corroborating evidence items with no conflicts")

    score = max(0.0, min(1.0, score))
    return round(score, 2), "; ".join(reasons)
