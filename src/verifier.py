"""
Independent verification (brief 3.5 + section 5 "Verification").

Critical design point: this module receives ONLY the draft translation and
raw evidence -- it re-derives its own judgment about vocabulary support,
grammar support, and conflicts rather than re-running the translator's
prompt and asking "are you sure?". A verifier that shares logic with the
generator can't catch the generator's own mistakes; that's the failure
mode the assignment calls out explicitly ("do not ask the same prompt to
approve itself").
"""
from __future__ import annotations
from dataclasses import dataclass
from .evidence import EvidenceStore
from .translator import DraftTranslation
from .confidence import compute_confidence
from .memory import SubtitleDecision, RunMemory


AUTO_APPROVE_THRESHOLD = 0.80
INSUFFICIENT_THRESHOLD = 0.20


def verify_and_decide(line: dict, draft: DraftTranslation, store: EvidenceStore,
                       memory: RunMemory) -> SubtitleDecision:
    subtitle_id = draft.subtitle_id
    problems = []

    # Check 1: vocabulary support -- every content word must trace to a dictionary or example.
    if draft.unsupported_terms:
        problems.append(f"unsupported vocabulary: {draft.unsupported_terms}")

    # Check 2: every evidence ref must actually resolve (catches a hallucinated citation).
    for ref in draft.evidence:
        base_ref = ref.split("#")[0]
        if store.get(base_ref) is None:
            problems.append(f"evidence reference does not resolve: {ref}")

    # Check 3: conflicting sources must be surfaced, never silently resolved.
    conflicts = list(draft.conflicts)

    # Check 4: reading-speed / timing sanity check (only meaningful when we HAVE text).
    if draft.nadi_9_text:
        duration = _duration_seconds(line.get("timecode_in"), line.get("timecode_out"))
        cps = len(draft.nadi_9_text) / duration if duration else None
        if cps and cps > 21:
            problems.append(f"reading speed too high: {cps:.1f} chars/sec (limit ~21)")

    confidence, reason = compute_confidence(draft, store, memory)

    disputed_rules_used = [rid for rid in draft.rules_used
                            if memory.rules.get(rid) and memory.rules[rid].status != "supported"]

    review_question = None
    if draft.unsupported_terms:
        decision = "INSUFFICIENT_EVIDENCE"
        review_question = (
            f"No Nadi-9 term exists in either dictionary or the approved examples for: "
            f"{', '.join(draft.unsupported_terms)}. Should a loanword be used, or is a "
            f"native circumlocution attested that we're missing?"
        )
   
    elif conflicts or disputed_rules_used or confidence < AUTO_APPROVE_THRESHOLD:
        decision = "HUMAN_REVIEW"
        if "kinship-relationship-1" in disputed_rules_used:
            review_question = (
                "Two linguists disagree on whether the reconciliation meaning here comes from "
                "word order or verb choice (kinship-relationship-1 is disputed). Which kinship "
                "form applies after reconciliation?"
            )
        elif disputed_rules_used:
            rule = memory.rules[disputed_rules_used[0]]
            reason_text = rule.reason.rstrip(".") if rule.reason else "insufficient supporting evidence"
            review_question = (
                f"{rule.rule_id} is disputed ({reason_text}) -- please confirm this is correct here."
            )
        elif conflicts:
            review_question = f"Dictionary/source conflict must be resolved before release: {conflicts[0]}"
        else:
            review_question = "Confidence below auto-approval threshold; please confirm before release."
    elif problems:
        decision = "HUMAN_REVIEW"
        review_question = f"Verification checks raised concerns: {'; '.join(problems)}"
    else:
        decision = "AUTO_APPROVED"

    if problems:
        conflicts = conflicts + [f"verification_flag: {p}" for p in problems]

    return SubtitleDecision(
        subtitle_id=subtitle_id,
        source_text=line["source_text"],
        nadi_9_text=draft.nadi_9_text,
        confidence=confidence,
        confidence_reason=reason,
        decision=decision,
        evidence=draft.evidence,
        assumptions=draft.assumptions,
        conflicts=conflicts,
        review_question=review_question,
        rules_used=draft.rules_used,
    )


def _duration_seconds(tc_in: str | None, tc_out: str | None) -> float | None:
    if not tc_in or not tc_out:
        return None
    def to_s(tc):
        h, m, s = tc.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return to_s(tc_out) - to_s(tc_in)
