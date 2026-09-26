"""
Structured run state: learned rules (claims), conflicts, subtitle decisions,
and the evidence -> claim -> subtitle backlink graph that makes targeted
replanning possible (brief section 3.7 "Replan when evidence changes" and
section 5 "Memory").

The backlink graph is the whole point: when a correction lands, replanner.py
asks this store "what depends on X" instead of anyone re-running everything.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class Rule:
    rule_id: str
    description: str
    category: str  # word_order | negation | tense | politeness | kinship | code_switching
    evidence: list[str]         # evidence refs, e.g. "approved_example:E07"
    counterexamples: list[str] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "candidate"   # candidate | supported | rejected | disputed
    reason: str = ""


@dataclass
class SubtitleDecision:
    subtitle_id: str
    source_text: str
    nadi_9_text: str | None
    confidence: float
    confidence_reason: str
    decision: str  # AUTO_APPROVED | HUMAN_REVIEW | INSUFFICIENT_EVIDENCE
    evidence: list[str]
    assumptions: list[str]
    conflicts: list[str]
    review_question: str | None
    rules_used: list[str] = field(default_factory=list)  # for backlink tracing


@dataclass
class RunMemory:
    rules: dict[str, Rule] = field(default_factory=dict)
    decisions: dict[str, SubtitleDecision] = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)
    change_log: list[dict] = field(default_factory=list)  # audit trail of replanning events

    def add_rule(self, rule: Rule):
        self.rules[rule.rule_id] = rule

    def add_decision(self, d: SubtitleDecision):
        self.decisions[d.subtitle_id] = d

    def record_conflict(self, description: str, refs: list[str]):
        self.conflicts.append({"description": description, "refs": refs})

    # ---- backlink queries used by replanner.py ----

    def subtitles_depending_on_evidence(self, evidence_ref: str) -> list[str]:
        out = []
        for sid, d in self.decisions.items():
            if evidence_ref in d.evidence:
                out.append(sid)
            else:
                # also catch indirect dependence via a rule that cites this evidence
                for rid in d.rules_used:
                    r = self.rules.get(rid)
                    if r and evidence_ref in r.evidence:
                        out.append(sid)
                        break
        return sorted(set(out))

    def rules_depending_on_evidence(self, evidence_ref: str) -> list[str]:
        return sorted(rid for rid, r in self.rules.items() if evidence_ref in r.evidence)

    def log_change(self, event: dict):
        event["sequence"] = len(self.change_log) + 1
        self.change_log.append(event)

    # ---- serialization for sample_run/ outputs ----

    def dump_rules(self, path: str | Path):
        Path(path).write_text(json.dumps(
            {rid: asdict(r) for rid, r in self.rules.items()}, indent=2, ensure_ascii=False
        ))

    def dump_decisions_jsonl(self, path: str | Path):
        with open(path, "w", encoding="utf-8") as f:
            for d in self.decisions.values():
                f.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")

    def dump_review_queue(self, path: str | Path):
        queue = [asdict(d) for d in self.decisions.values() if d.decision != "AUTO_APPROVED"]
        Path(path).write_text(json.dumps(queue, indent=2, ensure_ascii=False))
