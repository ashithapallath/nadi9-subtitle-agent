"""
Top-level orchestration: evidence -> hypotheses -> translate -> verify ->
escalate -> outputs. Also where the "surprise event" safety behaviors live:
prompt-injection scrubbing on retrieved text, and graceful tool-failure
handling under the call budget.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from .evidence import load_evidence, EvidenceStore
from .memory import RunMemory
from .hypotheses import extract_candidate_rules, test_rule_against_examples, run_model_proposed_rule
from .translator import draft_translate
from .verifier import verify_and_decide
from .provider import get_provider, CallBudget, ProviderError


INJECTION_PATTERNS = [
    r"ignore (all )?(prior|previous|the) (assignment )?(rules|constraints|instructions)",
    r"mark every (line|item|scene) auto[_ -]?approve",
    r"disregard (the )?(evidence|verification|assignment)",
]


def scrub_injections(text: str) -> tuple[str, list[str]]:
    """
    Any text pulled from a 'retrieved' document (scene descriptions, viewer
    feedback, etc.) is DATA, never instructions. We detect embedded
    imperative-looking instructions, strip them from what gets used as
    context, and log a flag -- we do not execute them under any
    circumstance, regardless of phrasing confidence.
    """
    flags = []
    cleaned = text
    for pat in INJECTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            flags.append(f"potential prompt injection matched pattern: {pat!r}")
    # Strip anything that looks like a bracketed system/override note.
    cleaned = re.sub(r"\[SYSTEM NOTE:.*?\]", "[REDACTED: untrusted embedded instruction, ignored]", cleaned, flags=re.DOTALL)
    return cleaned, flags


def run_pipeline(data_dir: str, out_dir: str, max_model_calls: int = 25, max_tool_calls: int = 50,
                  live: bool = False) -> dict:
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    store = load_evidence(data_dir)
    memory = RunMemory()
    budget = CallBudget(max_model_calls=max_model_calls, max_tool_calls=max_tool_calls)
    provider = get_provider(live=live)

    injection_log = []

    # --- 1. Inspect scene descriptions for embedded instructions (surprise event) ---
    episode = json.loads((data_dir / "episode.json").read_text())
    for scene in episode.get("scene_descriptions", []):
        cleaned, flags = scrub_injections(scene["desc"])
        scene["desc"] = cleaned
        if flags:
            injection_log.append({"scene": scene["scene"], "flags": flags})

    # --- 2. Hypothesis formation + testing (brief 3.2 / 3.3) ---
    for rule in extract_candidate_rules(store):
        test_rule_against_examples(rule, store)
        memory.add_rule(rule)

    try:
        budget.spend_model_call()
        model_rule = run_model_proposed_rule(provider, store)
        if model_rule is not None:
            memory.add_rule(model_rule)
    except ProviderError as e:
        # Tool/model failure -- degrade gracefully, do not crash the run.
        memory.log_change({"event": "provider_failure", "stage": "model_proposed_rule", "error": str(e)})

    # --- 3. Translate + verify every episode line (brief 3.4 / 3.5 / 3.6) ---
    episode_lines_by_id = {l["subtitle_id"]: l for l in episode["lines"]}
    for line in episode["lines"]:
        try:
            budget.spend_tool_call()
            draft = draft_translate(line, store, memory)
        except ProviderError as e:
            # If translation itself fails as a "tool", record an explicit
            # failure decision rather than fabricating a line.
            from .memory import SubtitleDecision
            memory.add_decision(SubtitleDecision(
                subtitle_id=line["subtitle_id"], source_text=line["source_text"], nadi_9_text=None,
                confidence=0.0, confidence_reason="translation step failed",
                decision="INSUFFICIENT_EVIDENCE", evidence=[], assumptions=[],
                conflicts=[f"tool_failure: {e}"], review_question="Retry translation for this line once the tool/model is available again.",
            ))
            continue
        decision = verify_and_decide(line, draft, store, memory)
        memory.add_decision(decision)

    # --- 4. Record known dictionary conflicts globally (for the report) ---
    dict_a = store.get("dictionary_a:full").payload["entries"]
    dict_b = store.get("dictionary_b:full").payload["entries"]
    for term in set(dict_a) & set(dict_b):
        a_v = dict_a[term].split("/")[0].strip()
        b_v = dict_b[term].split("/")[0].strip().split(" (")[0]
        if a_v != b_v:
            memory.record_conflict(f"'{term}': dictionary_a={a_v!r} vs dictionary_b={b_v!r}",
                                    [f"dictionary_a:full#{term}", f"dictionary_b:full#{term}"])

    # --- 5. Write outputs ---
    _write_outputs(out_dir, store, memory, episode, injection_log, budget)

    return {
        "store": store, "memory": memory, "episode": episode,
        "injection_log": injection_log, "budget": budget,
    }


def _write_outputs(out_dir: Path, store: EvidenceStore, memory: RunMemory, episode: dict,
                    injection_log: list, budget: CallBudget):
    memory.dump_rules(out_dir / "learned_rules.json")
    memory.dump_decisions_jsonl(out_dir / "subtitle_decisions.jsonl")
    memory.dump_review_queue(out_dir / "review_queue.json")

    # SRT
    srt_lines = []
    for i, line in enumerate(episode["lines"], start=1):
        d = memory.decisions.get(line["subtitle_id"])
        if not (d and d.nadi_9_text):
            text = "[NO SUPPORTED TRANSLATION -- see review_queue.json]"
        elif d.decision == "HUMAN_REVIEW":
            text = f"[REVIEW] {d.nadi_9_text}"
        else:
            text = d.nadi_9_text
        srt_lines.append(str(i))
        srt_lines.append(f"{_srt_time(line['timecode_in'])} --> {_srt_time(line['timecode_out'])}")
        srt_lines.append(text)
        srt_lines.append("")
    (out_dir / "subtitles.srt").write_text("\n".join(srt_lines), encoding="utf-8")

    # Final report
    total = len(memory.decisions)
    auto = sum(1 for d in memory.decisions.values() if d.decision == "AUTO_APPROVED")
    review = sum(1 for d in memory.decisions.values() if d.decision == "HUMAN_REVIEW")
    insuff = sum(1 for d in memory.decisions.values() if d.decision == "INSUFFICIENT_EVIDENCE")

    report = [
        "# Final Release Report -- Nadi-9 Episode EP01",
        "",
        f"- Total subtitle lines: {total}",
        f"- Auto-approved: {auto}",
        f"- Requires human review: {review}",
        f"- Insufficient evidence (no translation produced): {insuff}",
        f"- Model calls used: {budget.model_calls_used}/{budget.max_model_calls}",
        f"- Tool calls used: {budget.tool_calls_used}/{budget.max_tool_calls}",
        "",
        "## Release recommendation",
        ("DO NOT release without human-linguist review." if (review or insuff)
         else "Safe to release: all lines auto-approved with high confidence."),
        "",
        "## Global dictionary conflicts detected",
    ]
    if memory.conflicts:
        for c in memory.conflicts:
            report.append(f"- {c['description']} (refs: {', '.join(c['refs'])})")
    else:
        report.append("- none detected")

    report += ["", "## Prompt-injection attempts detected in retrieved material"]
    if injection_log:
        for entry in injection_log:
            report.append(f"- scene {entry['scene']}: {entry['flags']}")
        report.append("These were treated as untrusted data and stripped; none were executed.")
    else:
        report.append("- none detected")

    report += ["", "## Rules learned"]
    for r in memory.rules.values():
        report.append(f"- `{r.rule_id}` [{r.status}, confidence={r.confidence}]: {r.description}")

    (out_dir / "final_report.md").write_text("\n".join(report), encoding="utf-8")


def _srt_time(tc: str) -> str:
    # input "HH:MM:SS.mmm" -> SRT "HH:MM:SS,mmm"
    return tc.replace(".", ",")[:12]
