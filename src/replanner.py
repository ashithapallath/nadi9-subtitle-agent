"""
Replanning on evidence change (brief 3.7 + surprise events: dictionary
poisoning, corrected examples, mid-run linguist correction).

The key behavior under test: trace a corrected word/rule to every impacted
subtitle and rerun ONLY the necessary checks -- not the whole pipeline.
This is what memory.py's backlink graph exists for.
"""
from __future__ import annotations
from .evidence import EvidenceStore
from .memory import RunMemory
from .translator import draft_translate
from .verifier import verify_and_decide
from .hypotheses import test_rule_against_examples


def apply_correction_and_replan(evidence_ref: str, field_path: str, new_value, reason: str,
                                 store: EvidenceStore, memory: RunMemory,
                                 episode_lines_by_id: dict) -> dict:
    """
    Returns a change report: what was corrected, which rules were
    re-tested, which subtitles were re-verified, and what changed for each.
    """
    old_value = store.apply_correction(evidence_ref, field_path, new_value, reason)

    # Decisions cite dictionary evidence at field granularity (e.g.
    # "dictionary_a:full#danger"), not just the source ("dictionary_a:full").
    # Search backlinks under both forms so a correction to one dictionary
    # entry doesn't get mistaken for touching the whole dictionary.
    field_key = field_path.split(".")[-1]
    field_ref = f"{evidence_ref}#{field_key}"

    affected_rules = sorted(set(memory.rules_depending_on_evidence(evidence_ref)
                                 + memory.rules_depending_on_evidence(field_ref)))
    affected_subtitles = sorted(set(memory.subtitles_depending_on_evidence(evidence_ref)
                                     + memory.subtitles_depending_on_evidence(field_ref)))

    rule_changes = []
    for rid in affected_rules:
        rule = memory.rules[rid]
        before_status, before_conf = rule.status, rule.confidence
        test_rule_against_examples(rule, store)
        rule_changes.append({
            "rule_id": rid,
            "status_before": before_status, "status_after": rule.status,
            "confidence_before": before_conf, "confidence_after": rule.confidence,
        })

    subtitle_changes = []
    for sid in affected_subtitles:
        line = episode_lines_by_id.get(sid)
        if not line:
            continue
        before = memory.decisions.get(sid)
        before_snapshot = {
            "nadi_9_text": before.nadi_9_text if before else None,
            "decision": before.decision if before else None,
            "confidence": before.confidence if before else None,
        }
        draft = draft_translate(line, store, memory)
        new_decision = verify_and_decide(line, draft, store, memory)
        memory.add_decision(new_decision)
        subtitle_changes.append({
            "subtitle_id": sid,
            "before": before_snapshot,
            "after": {
                "nadi_9_text": new_decision.nadi_9_text,
                "decision": new_decision.decision,
                "confidence": new_decision.confidence,
            },
        })

    report = {
        "corrected_evidence": evidence_ref,
        "field_path": field_path,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "rules_retested": rule_changes,
        "subtitles_reverified": subtitle_changes,
        "untouched_subtitle_count": len(memory.decisions) - len(subtitle_changes),
    }
    memory.log_change({
        "event": "correction",
        "evidence_ref": evidence_ref,
        "affected_rules": affected_rules,
        "affected_subtitles": affected_subtitles,
        "reason": reason,
    })
    return report
