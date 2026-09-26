"""
Surprise event: "The available model or transcription tool may temporarily
fail." The pipeline must degrade gracefully -- record an explicit,
reviewable failure state for the affected item -- rather than crash the
whole run or silently skip the line.
"""
import pytest
from src.provider import CallBudget, ProviderError, MockProvider
from src.pipeline import run_pipeline
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data"


def test_call_budget_exhaustion_raises_not_silently_continues():
    budget = CallBudget(max_model_calls=1, max_tool_calls=1)
    budget.spend_model_call()
    with pytest.raises(ProviderError):
        budget.spend_model_call()
    budget.spend_tool_call()
    with pytest.raises(ProviderError):
        budget.spend_tool_call()


def test_pipeline_completes_even_with_a_very_tight_tool_budget(tmp_path):
    # With a tool-call budget too small to cover every line, the pipeline
    # must still finish and leave a reviewable trail for whatever it
    # couldn't process, instead of raising all the way out.
    result = run_pipeline(str(DATA_DIR), str(tmp_path), max_model_calls=25, max_tool_calls=2)
    memory = result["memory"]
    assert len(memory.decisions) >= 1
    failed = [d for d in memory.decisions.values() if any("tool_failure" in c for c in d.conflicts)]
    if len(result["episode"]["lines"]) > 2:
        assert failed, "lines beyond the tool budget should be recorded as explicit failures, not silently dropped"
    for d in failed:
        assert d.decision == "INSUFFICIENT_EVIDENCE"
        assert d.review_question is not None
