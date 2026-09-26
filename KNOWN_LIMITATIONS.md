# Known Limitations

Left intentionally incomplete given the 10-12 hour budget, in rough priority
order of what I'd tackle next:

1. **No real audio transcription.** `audio_interviews.json` is a pre-written
   summary rather than raw audio run through a transcription tool. A real
   build would add a `transcribe.py` tool call (budgeted, with a mock mode)
   and let the hypothesis engine cite specific timestamped utterances rather
   than a human-written summary of the interview.
2. **Rule extraction is templated, not fully generative.** `hypotheses.py`
   extracts a fixed set of candidate rule *shapes* (negation, politeness,
   kinship-relationship) and tests them against evidence, rather than
   open-endedly discovering novel rule shapes from the corpus. This was a
   deliberate tradeoff for auditability within the time budget — every rule
   the system considers is traceable to a specific, inspectable check. A
   more open-ended version would need a stronger verification layer to
   compensate (more counterexample mining, cross-validation across held-out
   examples).
3. **No explicit scene-risk prioritization pass.** The brief asks the
   planner to "prioritize risky scenes." Today, risk surfaces implicitly
   (novel constructions fall through to lower-confidence paths), but there's
   no separate planning step that looks at the whole episode up front and
   orders work by predicted difficulty before translating.
4. **Dictionary conflict resolution policy is simple.** When A and B
   disagree, the system always prefers B and flags the conflict. A fuller
   system would weigh per-entry corroboration (does an approved example or
   audio interview support A or B specifically?) rather than a fixed
   source-level preference.
5. **No web UI / no rendered video.** Per the brief, this is optional and
   deprioritized in favor of a correct, testable decision pipeline.
6. **Single-episode scope.** Cross-episode consistency (a rule learned in
   episode 1 carrying into episode 2 with appropriate confidence decay if
   unused for a while) isn't modeled — see `ARCHITECTURE.md`'s "how this
   scales" section for the intended direction.
7. **Viewer feedback is under-used.** It's loaded and reliability-scored but
   not yet wired into hypothesis testing (e.g. VF01's correction report
   about "na khaili" being a statement, not a question, isn't automatically
   cross-checked against the relevant subtitle decision). A real build would
   have the replanner treat a strong viewer correction similarly to a
   linguist correction, gated by a higher trust threshold.
8. **Synthetic evidence pack.** As noted in `README.md` and
   `AI_COLLABORATION.md`, `sample_data/` is built to the assignment's
   specification but is not the real supplied material — swapping in the
   real files (matching the same filenames/shapes) should require no code
   changes, but that swap itself hasn't been tested against real data.
9. **Audio interview coverage is partial.** The brief specifies 5 audio
   interviews; the synthetic pack built here includes 3 (`AI01`-`AI03`).
   This was a time-scoping choice given the 10-12 hour budget. The
   mechanism for handling audio evidence -- reliability scoring
   (including the secondhand-knowledge penalty seen in `AI03`), citation
   format, and integration into the evidence store -- is fully built and
   would extend to the remaining interviews with no code changes, only
   additional data files.
10. **Audio interviews and the grammar note inform reasoning but aren't
    formally cited as evidence.** `AI03` directly explains *why*
    `respect-2` is low-confidence ("admits she rarely uses this register
    herself... secondhand knowledge, lower reliability for this specific
    register"), and `grammar_note.md` items 4 and 5 are the original
    source of both the `respect-2` and `kinship-relationship-1` disputes --
    the `reason` text on both rules is clearly derived from it. But
    neither source appears in either rule's `evidence` list in
    `learned_rules.json`; only `approved_example` and `expert_note`
    citations are wired into the formal evidence-linking system. This is
    a real gap given how heavily the evaluation weights evidence-based
    reasoning: the most relevant supporting evidence for two disputed
    rules exists in the pack but isn't inspectable through the same
    citation mechanism as the rest. A fuller build would extend
    `evidence.py`'s citation format to audio interviews and the grammar
    note directly, so `learned_rules.json` could cite e.g.
    `audio_interview:AI03` and `grammar_note:section-4` alongside the
    existing evidence types.
11. **`respect-2` is missing one of its own two cited examples.** The
    rule's `reason` field states it's supported by "only 2 supporting
    examples," but its `evidence` list contains only `approved_example:E09`.
    `E10` ("Friend, will you come tomorrow?" -> casual `-ibu` ending,
    contrasting with E09's formal `-ibe`) is almost certainly the second
    example the grammar note is referring to, but it's not linked. Caught
    by reading the rule's own reason text against its evidence list rather
    than assuming the two were kept in sync.
12. **Multi-word dictionary terms aren't handled by the composition path.**
    Both dictionaries key kinship terms as the phrase `"elder brother"`
    (Dictionary B has no separate `"elder"` or `"brother"` entry). The
    translator's tokenizer splits on whitespace and looks up each word
    individually, so a novel sentence using "elder brother" that didn't
    happen to match an approved example word-for-word would incorrectly
    return `INSUFFICIENT_EVIDENCE` for "elder," even though the concept is
    dictionary-supported. This doesn't affect any of the 9 current episode
    lines (they all hit the exact-match path first), but it's a real gap
    in the dictionary-composition logic that a larger episode would likely
    expose. A fuller build would need multi-word phrase matching before
    falling back to single-token lookup.

## Decisions that should never be automated

- Final release sign-off for any line marked `HUMAN_REVIEW` or
  `INSUFFICIENT_EVIDENCE` (final_report.md's recommendation is intentionally
  conservative: any non-`AUTO_APPROVED` line blocks release).
- Resolving genuine expert disagreement (e.g. `kinship-relationship-1`) —
  the system's job is to surface the disagreement precisely, not adjudicate it.
- Deciding whether a loanword is acceptable for a term with zero native
  attestation (`S007`, "drone") — that's a cultural/editorial call.
