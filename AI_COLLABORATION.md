# AI Collaboration Log

This project was built with Claude as a collaborator. In the interest of
honesty about the "Use of AI tools" evaluation criterion, here's what it
actually did, and what I (would) change or reject when I sit down with the
real assignment pack instead of the synthetic one built here.

## What Claude was used for

- Scaffolding the module boundaries (`evidence` / `hypotheses` / `translator`
  / `verifier` / `confidence` / `memory` / `replanner`) so that generation
  and verification are structurally separate rather than one big prompt —
  this was a direct response to the brief's explicit warning against
  "the same prompt approving itself."
- Drafting the synthetic evidence pack (`sample_data/`) to match every
  material type the brief lists, including deliberately building in the
  contradictions the brief calls out (two dictionaries disagreeing, two
  examples flagged for later challenge, two experts disagreeing on a
  mechanism, one embedded prompt-injection string).
- Writing the first draft of each module's logic and the test suite.
- Writing this documentation set.

## What I verified / would verify before submitting for real

- **Ran every mode** (`run`, `demo-correction`, `demo-poison`) and inspected
  the actual JSON/SRT output line by line rather than trusting that the code
  "looked right" — this caught two real bugs during development (see below).
- **Ran the full test suite** (`pytest tests/ -v`, 10/10 passing) rather than
  assuming Claude's own claim that tests would pass.
- Checked the confidence/decision logic by hand against the assignment's
  stated principle ("a well-supported rule shouldn't itself lower
  confidence") and found the first draft was wrong.

## What Claude got wrong, that I caught and rejected

1. **Confidence capping was too blunt.** The first draft capped confidence
   to 0.55 whenever *any* rule was used in a derivation — including
   `negation-1`, which is a well-supported rule with no dispute attached.
   That would have sent every negated sentence to human review for no good
   reason, which defeats the point of having a confident, well-tested rule
   at all. I traced this by hand from the `subtitle_decisions.jsonl` output
   (line S009 was flagged `HUMAN_REVIEW` with a reason that didn't match its
   actual evidence quality) and had it rewritten to only cap confidence when
   a *disputed/candidate* rule specifically was load-bearing.
2. **Same bug, decision-routing side.** The verifier had the identical issue
   one layer up — `elif conflicts or draft.rules_used or confidence < ...`
   would route to `HUMAN_REVIEW` for any rule use at all. Fixed alongside
   #1, with a dedicated `disputed_rules_used` check.
3. **The poisoned-dictionary demo initially did nothing.** The first version
   of the episode data had every line matching an approved example
   word-for-word, so no line ever actually exercised the dictionary lookup
   path — meaning a "poisoned dictionary entry" correction had zero
   observable effect, which would have looked like a broken feature to an
   evaluator. I added a line (`S009`, "Not go, danger.") specifically
   constructed to bypass the exact-match path and hit the dictionary
   composition logic, and re-verified the correction produced a real,
   visible change (`HUMAN_REVIEW` -> `AUTO_APPROVED`, confidence 0.56 ->
   0.80) once the poisoned entry was removed.
4. **Backlink matching granularity.** The correction/replanner code first
   searched for backlinks using the bare source ref (`dictionary_a:full`),
   but decisions cite evidence at field granularity
   (`dictionary_a:full#danger`). This silently found zero affected
   subtitles for a correction that should have affected one. Caught the
   same way as #3 — by actually reading the JSON output, not by reading the
   code and assuming it was right.

## Bugs caught in a later review pass

After the initial build, I went back through the actual output files
line by line, cross-referencing `subtitle_decisions.jsonl` against
`learned_rules.json` rather than trusting that a passing test suite meant
every subtitle was reasoned about correctly. That caught four more issues:

5. **A disputed rule wasn't being attached to the subtitle it actually
   governed.** `respect-2` (confidence 0.35, disputed) exists specifically
   because of the formal `-ibe` verb ending seen in approved example E09.
   Subtitle S004 ("Sir, will you come tomorrow?") matches E09 exactly and
   uses that same `-ibe` form — but it was auto-approved at confidence 0.8
   with an empty `rules_used` list. The root cause: the exact-match
   translation path in `translator.py` only checked for disputed-rule
   dependency in one hardcoded special case (`kinship-relationship-1`), not
   generically for any rule. So a subtitle could rest entirely on an
   unresolved grammar rule and still sail through as fully approved. I
   found this by asking, for every rule marked `disputed` in
   `learned_rules.json`, "does any approved subtitle actually cite this
   rule's evidence without listing the rule itself?" — S004/respect-2 was
   exactly that case. Fixed by adding a generic check: before returning an
   exact-match translation, the translator now scans all rules still in
   `disputed`/`candidate` status and attaches any whose evidence overlaps
   with what was just cited. S004 now correctly comes out at confidence
   0.55 and routes to `HUMAN_REVIEW`.
6. **Duplicate evidence citations.** The same code path behind bug #5 also
   appended `approved_example:E04` twice into S003's evidence list — the
   exact-match branch never deduplicated its evidence, unlike the
   dictionary-composition branch a few lines below it, which already did.
   Fixed by adding the same `sorted(set(evidence))` deduplication to the
   exact-match return path.
7. **Review questions weren't specific once a second disputed rule existed.**
   Once #5 was fixed, S004 was correctly routed to `HUMAN_REVIEW`, but its
   `review_question` fell back to a generic "confidence below threshold"
   message, because `verifier.py` only had a hand-written specific question
   for the one hardcoded `kinship-relationship-1` case. I generalized this
   so any disputed rule used in a derivation produces a specific question
   built from that rule's own stored `reason` field, e.g. "respect-2 is
   disputed (only 2 supporting examples) -- please confirm this is correct
   here" instead of a generic fallback.
8. **The SRT output didn't visually flag review lines.** `subtitles.srt`
   showed `HUMAN_REVIEW` lines with no visible difference from
   `AUTO_APPROVED` lines -- only lines with `INSUFFICIENT_EVIDENCE` got a
   placeholder. Someone skimming the raw `.srt` file without also opening
   `review_queue.json` would have no way to tell a reviewed-but-uncertain
   line from a fully trusted one. Added a `[REVIEW]` prefix in
   `pipeline.py`'s SRT writer for any line whose decision is
   `HUMAN_REVIEW`.

None of these were caught by the test suite, since the tests check for
category-level behavior (a conflict gets flagged, an unsupported term gets
rejected, a correction propagates correctly) rather than checking every
individual subtitle's specific rule attribution. That's itself a real
known gap -- see `KNOWN_LIMITATIONS.md` candidate: a test asserting that
every subtitle whose evidence overlaps a disputed rule's evidence must list
that rule in `rules_used` would have caught bug #5 automatically instead of
requiring a manual audit.

## What I would not accept as-is if this were a real submission

- The synthetic evidence pack is a stand-in (documented explicitly in
  `README.md`) — it should never be presented as if it were the real
  supplied material.
- The `MockProvider`'s "confidently wrong grammar rule" and "fluent guess"
  behaviors are illustrative simulations of what an LLM might do, not a
  claim that this is exhaustive of how a real model could fail.