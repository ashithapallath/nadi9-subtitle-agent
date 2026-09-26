"""
Evidence loading and source-precedence scoring.

Design principle (per brief section 5, "Source handling"): we do NOT
blindly trust the largest or newest file. Each source gets an explicit,
inspectable reliability score derived from *type*, *provenance* and
*corroboration* -- never from size alone. This module is the one place
that decision is made, so it can be audited and argued with.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Source-type base reliability. These are starting priors, not final
# verdicts -- corroboration/conflict adjust them per-claim (see memory.py).
SOURCE_TYPE_BASE_RELIABILITY = {
    "grammar_note": 0.65,       # structured but self-admits incompleteness
    "expert_note": 0.75,        # human specialists, but they disagree with each other
    "dictionary_b": 0.70,       # small, curated, native-speaker fieldwork
    "dictionary_a": 0.55,       # broad coverage but provenance of entries is undocumented
    "audio_interview": 0.60,    # native speaker ground truth, hurt by audio quality/secondhand knowledge
    "approved_example": 0.80,   # highest baseline -- these are the ground-truth translation pairs
    "viewer_feedback": 0.35,    # useful signal possible, but high noise, not vetted
}


@dataclass
class EvidenceItem:
    source_type: str
    source_id: str
    payload: dict
    reliability: float
    notes: str = ""


@dataclass
class EvidenceStore:
    items: dict[str, EvidenceItem] = field(default_factory=dict)
    # tracks corrections applied over time, for auditability
    correction_log: list[dict] = field(default_factory=list)

    def add(self, item: EvidenceItem):
        self.items[f"{item.source_type}:{item.source_id}"] = item

    def get(self, ref: str) -> EvidenceItem | None:
        return self.items.get(ref)

    def all_of_type(self, source_type: str) -> list[EvidenceItem]:
        return [i for i in self.items.values() if i.source_type == source_type]

    def apply_correction(self, ref: str, field_path: str, new_value: Any, reason: str):
        """
        A correction event (linguist correction, discovered dictionary
        poisoning, a previously-approved example turning out to be wrong).
        We log every correction with a reason and timestamp-equivalent
        sequence number, so replanner.py can find every subtitle that
        depended on the old value.
        """
        item = self.items.get(ref)
        old_value = None
        if item is not None:
            keys = field_path.split(".")
            node = item.payload
            for k in keys[:-1]:
                node = node[k]
            old_value = node.get(keys[-1])
            node[keys[-1]] = new_value
        self.correction_log.append({
            "ref": ref,
            "field_path": field_path,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "sequence": len(self.correction_log) + 1,
        })
        return old_value


def load_evidence(data_dir: str | Path) -> EvidenceStore:
    data_dir = Path(data_dir)
    store = EvidenceStore()

    examples = json.loads((data_dir / "examples.json").read_text())
    for ex in examples:
        rel = SOURCE_TYPE_BASE_RELIABILITY["approved_example"]
        if ex.get("flagged_for_review"):
            rel -= 0.15  # brief: "two examples may later be challenged"
        store.add(EvidenceItem("approved_example", ex["id"], ex, rel,
                                notes="flagged_for_review" if ex.get("flagged_for_review") else ""))

    dict_a = json.loads((data_dir / "dictionary_a.json").read_text())
    store.add(EvidenceItem("dictionary_a", "full", dict_a,
                            SOURCE_TYPE_BASE_RELIABILITY["dictionary_a"],
                            notes=dict_a["meta"]["note"]))

    dict_b = json.loads((data_dir / "dictionary_b.json").read_text())
    store.add(EvidenceItem("dictionary_b", "full", dict_b,
                            SOURCE_TYPE_BASE_RELIABILITY["dictionary_b"],
                            notes=dict_b["meta"]["note"]))

    grammar_text = (data_dir / "grammar_notes.md").read_text()
    store.add(EvidenceItem("grammar_note", "v1", {"text": grammar_text},
                            SOURCE_TYPE_BASE_RELIABILITY["grammar_note"]))

    experts = json.loads((data_dir / "expert_notes.json").read_text())
    for e in experts:
        store.add(EvidenceItem("expert_note", e["id"], e,
                                SOURCE_TYPE_BASE_RELIABILITY["expert_note"]))

    feedback = json.loads((data_dir / "viewer_feedback.json").read_text())
    for f in feedback:
        rel = SOURCE_TYPE_BASE_RELIABILITY["viewer_feedback"]
        if f.get("type") == "correction_report":
            rel += 0.1  # corroborated-by-content bump; still capped below experts
        store.add(EvidenceItem("viewer_feedback", f["id"], f, rel))

    audio = json.loads((data_dir / "audio_interviews.json").read_text())
    for a in audio:
        rel = SOURCE_TYPE_BASE_RELIABILITY["audio_interview"]
        if "secondhand" in a.get("quality_note", "").lower():
            rel -= 0.15
        store.add(EvidenceItem("audio_interview", a["id"], a, rel))

    return store
