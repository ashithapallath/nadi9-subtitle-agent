"""
CLI entrypoint. Run with no arguments for the default replay-mode run:

    python -m src.cli run

See README.md for the full command list (run / correct / demo-events).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_pipeline
from .replanner import apply_correction_and_replan


def main(argv=None):
    parser = argparse.ArgumentParser(prog="nadi9")
    parser.add_argument("--data-dir", default="sample_data")
    parser.add_argument("--out-dir", default="sample_run")
    parser.add_argument("--max-model-calls", type=int, default=25)
    parser.add_argument("--max-tool-calls", type=int, default=50)
    parser.add_argument("--live", action="store_true",
                         help="Use a real Anthropic model call if ANTHROPIC_API_KEY is set. "
                              "Default (no flag) is the deterministic offline mock provider.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Run the full pipeline end to end (default mode).")

    p_correct = sub.add_parser("demo-correction",
                                help="Run the pipeline, then apply a sample linguist correction "
                                     "mid-stream and show targeted replanning (surprise event demo).")

    sub.add_parser("demo-poison",
                    help="Run the pipeline, then simulate discovering a poisoned dictionary "
                         "entry and correct it, showing which subtitles were affected.")

    args = parser.parse_args(argv)

    if args.command == "run":
        result = run_pipeline(args.data_dir, args.out_dir, args.max_model_calls,
                               args.max_tool_calls, live=args.live)
        _print_summary(result)

    elif args.command == "demo-correction":
        result = run_pipeline(args.data_dir, args.out_dir, args.max_model_calls,
                               args.max_tool_calls, live=args.live)
        episode_lines_by_id = {l["subtitle_id"]: l for l in result["episode"]["lines"]}
        # Simulate: a linguist reviews expert_note:EXP01/EXP02 and settles the dispute,
        # confirming Dr. Rao's word-order account and correcting example E04's gloss note.
        report = apply_correction_and_replan(
            evidence_ref="expert_note:EXP03",
            field_path="note",
            new_value="RESOLVED 2024-06-01: field consensus confirms Dr. Rao's word-order "
                      "account; verb choice ('firli' vs 'aau') is a secondary marker, not primary.",
            reason="Linguist correction arrived mid-processing, resolving the kinship-relationship-1 dispute.",
            store=result["store"], memory=result["memory"], episode_lines_by_id=episode_lines_by_id,
        )
        Path(args.out_dir, "correction_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.command == "demo-poison":
        result = run_pipeline(args.data_dir, args.out_dir, args.max_model_calls,
                               args.max_tool_calls, live=args.live)
        episode_lines_by_id = {l["subtitle_id"]: l for l in result["episode"]["lines"]}
        # Simulate discovering that dictionary_a's "danger" entry was poisoned
        # (deliberately wrong / unsafe) and correcting it.
        report = apply_correction_and_replan(
            evidence_ref="dictionary_a:full",
            field_path="entries.danger",
            new_value="[REMOVED: entry found to be poisoned/unreliable, do not use]",
            reason="Post-hoc audit found dictionary_a's 'danger' entry was deliberately corrupted.",
            store=result["store"], memory=result["memory"], episode_lines_by_id=episode_lines_by_id,
        )
        Path(args.out_dir, "poison_correction_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps(report, indent=2, ensure_ascii=False))


def _print_summary(result):
    memory = result["memory"]
    total = len(memory.decisions)
    auto = sum(1 for d in memory.decisions.values() if d.decision == "AUTO_APPROVED")
    review = sum(1 for d in memory.decisions.values() if d.decision == "HUMAN_REVIEW")
    insuff = sum(1 for d in memory.decisions.values() if d.decision == "INSUFFICIENT_EVIDENCE")
    print(f"Run complete. {total} lines processed: {auto} auto-approved, "
          f"{review} need human review, {insuff} insufficient evidence.")
    print(f"Model calls used: {result['budget'].model_calls_used}/{result['budget'].max_model_calls}")
    print(f"Outputs written to: {args_out_dir(result)}")


def args_out_dir(result):
    return "sample_run"  # informational only; actual path is whatever --out-dir was


if __name__ == "__main__":
    main()
