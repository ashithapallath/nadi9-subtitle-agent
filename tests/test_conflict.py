"""
Surprise event: two previously-approved examples / two dictionaries
disagree. The system must surface the conflict, never silently pick a
winner without flagging it, and must route the affected subtitle to
human review.
"""
from src.translator import draft_translate
from src.verifier import verify_and_decide


def test_dictionary_conflict_is_surfaced_and_forces_review(store, memory_with_rules):
    line = {"subtitle_id": "TEST01", "source_text": "Not go, danger.",
            "timecode_in": "00:00:00.000", "timecode_out": "00:00:03.000"}
    draft = draft_translate(line, store, memory_with_rules)
    assert draft.conflicts, "dictionary_a/dictionary_b disagree on 'danger' -- must be flagged"
    decision = verify_and_decide(line, draft, store, memory_with_rules)
    assert decision.decision == "HUMAN_REVIEW"
    assert decision.conflicts
    assert decision.review_question is not None


def test_same_source_sentence_two_examples_conflict_is_flagged(store, memory_with_rules):
    # "You came back, elder brother?" has two approved examples (E04, E07)
    # with DIFFERENT Nadi-9 text depending on relationship state.
    line = {"subtitle_id": "TEST02", "source_text": "You came back, elder brother?",
            "timecode_in": "00:00:00.000", "timecode_out": "00:00:03.000"}
    draft = draft_translate(line, store, memory_with_rules)
    assert draft.conflicts, "conflicting approved examples for the same sentence must be surfaced"
    decision = verify_and_decide(line, draft, store, memory_with_rules)
    assert decision.decision == "HUMAN_REVIEW"
    assert "kinship-relationship-1" in decision.rules_used
