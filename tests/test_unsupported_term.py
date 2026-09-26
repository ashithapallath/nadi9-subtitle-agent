"""
The system must never invent a plausible-looking Nadi-9 word for a term
with zero evidence support (brief: "Abstention: prefer a precise review
request over a fluent but unsupported invention"). This also guards
against the mock provider's simulated "confident but baseless" behavior.
"""
from src.translator import draft_translate
from src.verifier import verify_and_decide


def test_unsupported_vocabulary_yields_insufficient_evidence_not_invention(store, memory_with_rules):
    line = {"subtitle_id": "TEST03", "source_text": "The drone flew over the village.",
            "timecode_in": "00:00:00.000", "timecode_out": "00:00:03.000"}
    draft = draft_translate(line, store, memory_with_rules)
    assert draft.unsupported_terms, "drone/village have no dictionary or example support"
    assert draft.nadi_9_text is None, "must not fabricate a translation for unsupported terms"

    decision = verify_and_decide(line, draft, store, memory_with_rules)
    assert decision.decision == "INSUFFICIENT_EVIDENCE"
    assert decision.nadi_9_text is None
    assert decision.review_question is not None
    assert decision.confidence == 0.0


def test_model_proposed_rule_with_no_evidence_is_rejected(store):
    from src.hypotheses import run_model_proposed_rule
    from src.provider import MockProvider

    provider = MockProvider(inject_unsupported_rule=True)
    rule = run_model_proposed_rule(provider, store)
    assert rule is not None
    assert rule.status == "rejected", "a model rule with zero verifiable evidence must never be trusted"
    assert rule.confidence == 0.0
    assert rule.evidence == []
