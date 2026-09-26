# Architecture Note

## 1. Planning

There is no single "translate the episode" prompt (the brief explicitly
scores this poorly). The run is a fixed pipeline of independently-testable
stages — `evidence -> hypotheses -> per-line translate -> per-line verify ->
escalate -> report` (`pipeline.py::run_pipeline`) — plus a separate
`replanner.py` path invoked only when new evidence arrives. Risk
prioritization happens implicitly through evidence reliability: exact
approved-example matches are tried before dictionary composition, so the
riskiest lines (novel constructions, disputed kinship forms) are exactly the
ones that fall through to the lower-confidence path and get flagged.

Given more time, the planner would be extended to explicitly rank *scenes*
by risk before translation (emotionally loaded scenes, scenes with disputed
kinship terms, scenes with modern loanwords) rather than only reacting
per-line — see `KNOWN_LIMITATIONS.md`.

## 2. Source handling and precedence

`evidence.py::SOURCE_TYPE_BASE_RELIABILITY` assigns a prior reliability by
**source type and provenance**, not recency or size:

| Source | Prior | Why |
|---|---|---|
| Approved example | 0.80 | Ground-truth pairs; the highest-trust artifact |
| Expert note | 0.75 | Human specialists, but they disagree with each other — see kinship-relationship-1 |
| Dictionary B | 0.70 | Small but curated, native-speaker fieldwork |
| Audio interview | 0.60 (−0.15 if self-reported secondhand) | Native ground truth, hurt by quality/hearsay |
| Grammar note | 0.65 | Structured but self-admits incompleteness |
| Dictionary A | 0.55 | Broad coverage, but entry-level provenance is undocumented — the larger dictionary is *not* trusted more for being larger |
| Viewer feedback | 0.35 (+0.10 if tagged `correction_report`) | High noise; only a mild signal boost when a comment looks like a real correction |

Two approved examples are marked `flagged_for_review` in the sample pack
(matching the brief's "two examples may later be challenged") and get a
reliability penalty rather than being trusted at face value.

Dictionary conflicts are detected exhaustively (`pipeline.py`, comparing
every shared key) and per-line whenever a conflicting term is actually used
(`translator.py`). When A and B disagree, the system prefers B (smaller,
curated) **but always records the conflict** rather than silently picking a
winner — the choice is visible and reversible.

## 3. Memory

`memory.py::RunMemory` holds three things: `rules` (hypotheses with
evidence/counterexamples/status), `decisions` (one `SubtitleDecision` per
line), and `conflicts`. Every `SubtitleDecision` records exactly which
evidence refs and which rule IDs it depended on. This backlink graph
(`subtitles_depending_on_evidence`, `rules_depending_on_evidence`) is what
makes targeted replanning possible without a vector index or re-running
everything — for this scale (one episode, ~20 examples) a simple in-memory
reverse index is sufficient and fully auditable; at scale this would move to
a real graph store (see "how this scales" below).

## 4. Tool use

Two "tools" exist in this system: the model provider (`propose_rule`,
`translate_line`) and the per-line translation step, both gated by a
`CallBudget` (default 25 model calls / 50 tool calls per episode, configurable
via CLI flags, matching the brief's budget constraint). Both raise
`ProviderError` on exhaustion or failure rather than silently degrading —
callers (`pipeline.py`) catch this and record an explicit, reviewable
failure state (`INSUFFICIENT_EVIDENCE` with a `tool_failure` conflict entry)
instead of crashing the whole run or fabricating output.

## 5. Verification — independence from generation

`verifier.py` does **not** call the same prompt that produced the
translation and ask "are you sure?" — the failure mode the brief calls out
by name. It re-derives judgment from primitives the translator already
exposed (unsupported terms, evidence refs, conflicts) plus checks the
translator has no reason to run itself: whether every cited evidence
reference actually resolves in the store (catches a hallucinated citation),
and a reading-speed/timing sanity check. Confidence (`confidence.py`) is a
third, separate module — it does not "trust" the verifier's PASS, it
recomputes a score from source reliability, conflict count, and whether a
*disputed* rule was load-bearing in the derivation (a well-supported rule
like `negation-1` does not itself lower confidence — only rules still in
`disputed`/`candidate` status do).

## 6. Failure recovery

- **Model/tool failure**: caught at the call site, turned into an explicit
  `INSUFFICIENT_EVIDENCE` decision with a `tool_failure` conflict tag and a
  concrete "retry this line" review question (`pipeline.py`,
  `tests/test_tool_failure.py`).
- **Model hallucinated grammar rule**: `hypotheses.py::run_model_proposed_rule`
  subjects any model-proposed rule to the exact same evidence-resolution
  check as a human-derived rule; a rule with no verifiable evidence is
  marked `rejected` with confidence 0.0 and is never applied
  (`tests/test_unsupported_term.py::test_model_proposed_rule_with_no_evidence_is_rejected`).
- **Prompt injection in retrieved text**: `pipeline.py::scrub_injections`
  pattern-matches imperative-looking embedded instructions in scene
  descriptions before they're used as context, redacts them, and logs the
  attempt — the injected text is data, never instructions, and this is
  enforced structurally (the pipeline has no code path that lets scene-
  description text change a decision threshold or bypass verification), not
  just by asking a model nicely (`tests/test_prompt_injection.py`).

## 7. Trust boundaries

- The model provider (mock or live) is trusted for *proposals* only —
  candidate rules, draft guesses — never for a final decision. Every
  proposal passes through the same evidence-gate as human-authored material.
- Retrieved/embedded text (scene descriptions, viewer feedback) is always
  data. It can inform assumptions but cannot alter thresholds, rules, or
  bypass a check.
- The `AUTO_APPROVED` / `HUMAN_REVIEW` / `INSUFFICIENT_EVIDENCE` distinction
  is the actual human/automation boundary: nothing marked anything other
  than `AUTO_APPROVED` should reach a viewer without a linguist's sign-off,
  and `final_report.md`'s release recommendation reflects that directly.

## How this would scale to 5,000 episodes / 40 dialects

- The in-memory `RunMemory` backlink graph becomes a real datastore (e.g. a
  small graph/relational schema: `evidence(id) -> claim(id) -> subtitle(id)`)
  so correction propagation is a query, not a Python loop over one episode's
  state.
- Evidence reliability priors become per-dialect config, not a shared
  constant — a dialect with a richer example set should lean less on
  dictionaries; the *mechanism* (type + provenance based scoring) stays the
  same.
- The call-budget object becomes a per-dialect, per-tenant rate limiter.
- Human-review queues would need per-dialect linguist routing and an SLA
  layer — out of scope here, but the `review_queue.json` shape is already
  the right unit of work to route.
