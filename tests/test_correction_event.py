"""
Surprise events: a linguist correction arrives mid-processing, and a
poisoned dictionary entry is discovered and corrected. In both cases the
system must trace the change to exactly the affected rules/subtitles and
leave everything else untouched -- not reprocess the whole episode.
"""
import json
from pathlib import Path
from src.pipeline import run_pipeline
from src.replanner import apply_correction_and_replan

DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data"


def test_poisoned_dictionary_entry_only_affects_dependent_subtitles(tmp_path):
    result = run_pipeline(str(DATA_DIR), str(tmp_path))
    store, memory = result["store"], result["memory"]
    episode_lines_by_id = {l["subtitle_id"]: l for l in result["episode"]["lines"]}

    total_before = len(memory.decisions)
    report = apply_correction_and_replan(
        evidence_ref="dictionary_a:full",
        field_path="entries.danger",
        new_value="[REMOVED: poisoned]",
        reason="test: poisoned entry discovered",
        store=store, memory=memory, episode_lines_by_id=episode_lines_by_id,
    )
    # Only the subtitle that actually used dictionary_a's 'danger' entry should be touched.
    assert report["subtitles_reverified"], "expected at least one dependent subtitle to be re-verified"
    assert len(report["subtitles_reverified"]) < total_before, "correction must be targeted, not global"
    assert report["untouched_subtitle_count"] == total_before - len(report["subtitles_reverified"])
    # The specific line that depended on the poisoned entry should improve once it's removed.
    touched_ids = [c["subtitle_id"] for c in report["subtitles_reverified"]]
    assert "S009" in touched_ids


def test_linguist_correction_updates_only_affected_rule(tmp_path):
    result = run_pipeline(str(DATA_DIR), str(tmp_path))
    store, memory = result["store"], result["memory"]
    episode_lines_by_id = {l["subtitle_id"]: l for l in result["episode"]["lines"]}

    report = apply_correction_and_replan(
        evidence_ref="expert_note:EXP03",
        field_path="note",
        new_value="RESOLVED: word order account confirmed.",
        reason="test: linguist correction mid-run",
        store=store, memory=memory, episode_lines_by_id=episode_lines_by_id,
    )
    assert report["reason"] == "test: linguist correction mid-run"
    assert any(rc["rule_id"] == "kinship-relationship-1" for rc in report["rules_retested"])
    # unrelated rules (e.g. negation-1) must NOT be retested by this correction
    assert not any(rc["rule_id"] == "negation-1" for rc in report["rules_retested"])
