# Nadi-9 Evidence-Grounded Subtitle Agent

An agentic system that learns a fictional dialect ("Nadi-9") from limited,
conflicting evidence and produces subtitle proposals that are honest about
what they don't know. Built for the "Learn a Dialect That Does Not Exist"
assignment.

## What this is (in one paragraph)

The system never asks a single LLM prompt "please translate this episode."
Instead it: loads and scores its evidence sources by provenance (not size);
extracts and tests grammar hypotheses against every approved example,
tracking counterexamples; drafts each subtitle line from *only* what's
supported by dictionaries/examples/rules; runs an independent verifier that
can reject the draft; computes a confidence score with an explicit written
reason; and routes anything uncertain, conflicting, or unsupported to a
human-review queue with a precise question instead of a fluent guess.

## Quick start

```bash
cd nadi9
python3 -m src.cli run
```

No API key needed — this runs in **offline replay mode** against the
deterministic `MockProvider` (see "Replay mode" below), using the mock
evidence pack in `sample_data/`. Outputs land in `sample_run/`:

- `subtitles.srt` — the subtitle file (lines needing review show a visible placeholder, never an invented guess)
- `subtitle_decisions.jsonl` — one structured decision object per line (see schema below)
- `learned_rules.json` — every grammar hypothesis, its status, confidence, and evidence
- `review_queue.json` — every line that needs a human linguist, with a specific question
- `final_report.md` — run summary + release recommendation

### Demo the surprise-event handling

```bash
python3 -m src.cli demo-correction   # a linguist correction arrives mid-run; only the affected rule/subtitle is re-verified
python3 -m src.cli demo-poison       # a poisoned dictionary entry is discovered and corrected; only dependent subtitles are re-verified
```

### Run the tests

```bash
   pip install pytest   # or use a venv; on Linux you may need: pip install pytest --break-system-packages
python3 -m pytest tests/ -v

```

Ten tests cover: a dictionary conflict, a same-sentence example conflict, an
unsupported term, a hallucinated model-proposed grammar rule, a mid-run
linguist correction, a poisoned dictionary entry, a tool/model failure under
a tight call budget, and a prompt-injection attempt embedded in retrieved
scene data.

## Replay mode vs. live mode

By default (`MockProvider`) the system is **fully offline and deterministic**
— this is what an evaluator should run, and it requires no API key. It
simulates the two provider-side behaviors the assignment explicitly calls
out as surprise events: a model that returns a confident-but-unsupported
grammar rule, and a "fluent guess" fallback for unsupported vocabulary
(exercised only through `provider.py`, never allowed to reach an actual
subtitle — see `verifier.py`).

Pass `--live` with `ANTHROPIC_API_KEY` set to route rule-proposal and
translation-assist calls through a real Claude call instead
(`src/provider.py::AnthropicProvider`). The rest of the pipeline —
evidence scoring, hypothesis testing, verification, confidence — is
identical in both modes, because the trust logic lives in the agent's
code, not in what the model says about itself.

## Note on the evidence pack

The actual assignment's supplied material (20 examples, 5 audio interviews,
two dictionaries, expert notes, viewer feedback, the episode package) was
not included in the candidate brief PDF itself — only the brief describing
its shape. `sample_data/` is a **faithful synthetic stand-in** built to the
same specification (same source types, same kinds of internal
contradictions, the same "two examples later challenged" detail, etc.), so
the architecture and every safety behavior can be demonstrated end to end.
Swapping in the real pack means only replacing the files under
`sample_data/` with matching filenames/shapes — no code changes required.

## Subtitle decision schema

```json
{
  "subtitle_id": "S003",
  "source_text": "You came back, elder brother?",
  "nadi_9_text": "dada ni firli mo?",
  "confidence": 0.55,
  "confidence_reason": "average source reliability 0.80 across 2 evidence item(s); -0.15 for 1 unresolved conflict(s); capped at 0.55: derivation relies on disputed rule(s) ['kinship-relationship-1']",
  "decision": "HUMAN_REVIEW",
  "evidence": ["approved_example:E04", "approved_example:E07"],
  "assumptions": ["spoken right after Amar and his brother reconcile following a long estrangement"],
  "conflicts": ["Multiple approved examples exist for this exact sentence with different Nadi-9 text..."],
  "review_question": "Two linguists disagree on whether the reconciliation meaning here comes from word order or verb choice. Which kinship form applies after reconciliation?",
  "rules_used": ["kinship-relationship-1"]
}
```

## Project layout

```
src/
  provider.py     LLM provider abstraction: MockProvider (default, offline) + AnthropicProvider (--live)
  evidence.py     Loads all sources, assigns provenance-based reliability scores
  memory.py       Structured run state: rules, decisions, conflicts, and the evidence->claim->subtitle backlink graph
  hypotheses.py   Extracts + tests grammar rules against examples; subjects model-proposed rules to the same test
  translator.py   Drafts a subtitle from evidence only (dictionary + rules); never invents unsupported words
  verifier.py     Independent checks (vocab support, evidence resolution, conflicts, timing); makes the AUTO/REVIEW/INSUFFICIENT call
  confidence.py   Confidence score + a written reason, computed from the same inputs the verifier used
  replanner.py    Traces a correction to exactly the affected rules/subtitles and re-verifies only those
  pipeline.py     Orchestrates the run; also scrubs embedded prompt-injection text from retrieved documents
  cli.py          Entry point (run / demo-correction / demo-poison)
tests/            One test file per surprise-event category (see above)
sample_data/      Synthetic evidence pack matching the brief's material list
sample_run/       Output of the last `run` (committed so evaluators can inspect without running anything)
```

See `ARCHITECTURE.md` for the design rationale, `AI_COLLABORATION.md` for
how AI assistance was used and checked, and `KNOWN_LIMITATIONS.md` for what
was intentionally left incomplete given the time budget.
