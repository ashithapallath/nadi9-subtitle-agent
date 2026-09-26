"""
Translation step (brief 3.4): produce a draft subtitle line using only
established rules + dictionary lookups, with explicit evidence citations
and assumptions. This step is deliberately dumb and auditable -- all the
judgment about whether to TRUST the draft happens later, independently,
in verifier.py. Translator and verifier must never be the same prompt
asking itself if it's right (brief section 5, "Verification").
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from .evidence import EvidenceStore
from .memory import RunMemory


STOPWORDS = {"a", "an", "the", "is", "it", "to", "will", "i", "you", "he", "she", "we", "please"}


def _tokenize(text: str) -> list[str]:
    return [t.lower().strip("?.,!") for t in text.split() if t.lower().strip("?.,!") not in STOPWORDS]


@dataclass
class DraftTranslation:
    subtitle_id: str
    nadi_9_text: str | None
    evidence: list[str]
    assumptions: list[str]
    conflicts: list[str]
    unsupported_terms: list[str]
    rules_used: list[str]


def draft_translate(line: dict, store: EvidenceStore, memory: RunMemory) -> DraftTranslation:
    subtitle_id = line["subtitle_id"]
    source = line["source_text"]
    tokens = _tokenize(source)

    dict_a = store.get("dictionary_a:full").payload["entries"]
    dict_b = store.get("dictionary_b:full").payload["entries"]

    words_out: list[str] = []
    evidence: list[str] = []
    assumptions: list[str] = []
    conflicts: list[str] = []
    unsupported_terms: list[str] = []
    rules_used: list[str] = []

    # 1. Exact-phrase check against approved examples first (highest-trust path).
    exact_match = None
    for item in store.all_of_type("approved_example"):
        if item.payload["source"].strip().lower().rstrip("?.") == source.strip().lower().rstrip("?."):
            exact_match = item
            break

    if exact_match is not None:
        evidence.append(f"approved_example:{exact_match.source_id}")
        candidate_text = exact_match.payload["nadi9"]

        # Special-case the disputed "dada" reunion pattern: two examples of the SAME
        # source sentence exist (E04 pre-reconciliation, E07 post-reconciliation) with
        # DIFFERENT Nadi-9 text. This is exactly the kind of thing that must be flagged,
        # not silently resolved by picking whichever example matched first.
        same_source_variants = [
            e for e in store.all_of_type("approved_example")
            if e.payload["source"].strip().lower().rstrip("?.") == source.strip().lower().rstrip("?.")
        ]
        if len(same_source_variants) > 1:
            for v in same_source_variants:
                evidence.append(f"approved_example:{v.source_id}")
            conflicts.append(
                "Multiple approved examples exist for this exact sentence with different "
                "Nadi-9 text depending on relationship state (kinship-relationship-1 is disputed): "
                + ", ".join(f"approved_example:{v.source_id}={v.payload['nadi9']!r}" for v in same_source_variants)
            )
            rules_used.append("kinship-relationship-1")
            assumptions.append(
                line.get("context_note", "No context note provided to disambiguate relationship state.")
            )
            # We still propose a best-guess (using the context note if present) but the
            # conflict + disputed rule will push this to HUMAN_REVIEW downstream.
            if line.get("context_note") and "reconcile" in line["context_note"].lower():
                candidate_text = next(
                    (v.payload["nadi9"] for v in same_source_variants if "reconcil" in v.payload["scene"].lower()),
                    candidate_text,
                )
                # Generic check: does the evidence we just cited also back some OTHER
        # rule that is still disputed/candidate? If so, this translation is
        # implicitly resting on that unresolved rule too, even though it came
        # from a fast exact-match lookup rather than dictionary composition.
        # (This is what should have caught respect-2 for "sahib ... ausibe".)
        for rule in memory.rules.values():
            if rule.status in ("disputed", "candidate") and rule.rule_id not in rules_used:
                if any(ev in rule.evidence for ev in evidence):
                    rules_used.append(rule.rule_id)

        evidence = sorted(set(evidence))  # dedupe -- fixes the duplicate E04 seen in S003

        return DraftTranslation(subtitle_id, candidate_text, evidence, assumptions, conflicts,
                                 unsupported_terms, rules_used)
        

    # 2. No exact match -> compose from dictionary + negation rule, word by word.
    negation_rule = memory.rules.get("negation-1")
    has_negation = "not" in tokens or " not " in f" {source.lower()} "
    if has_negation and negation_rule and negation_rule.status == "supported":
        rules_used.append("negation-1")
        evidence.extend(negation_rule.evidence[:2])

    for tok in tokens:
        if tok == "not":
            continue
        a_val = dict_a.get(tok)
        b_val = dict_b.get(tok)
        if isinstance(a_val, str) and a_val.startswith("[REMOVED"):
            a_val = None
        if isinstance(b_val, str) and b_val.startswith("[REMOVED"):
            b_val = None
        if a_val and b_val and a_val.split("/")[0].strip() != b_val.split("/")[0].strip().split(" (")[0]:
            conflicts.append(f"dictionary:A:{tok} ({a_val!r}) vs dictionary:B:{tok} ({b_val!r})")
            words_out.append(b_val.split("/")[0].strip())  # prefer curated Dictionary B, but flag the conflict
            evidence.append(f"dictionary_b:full#{tok}")
            evidence.append(f"dictionary_a:full#{tok}")
        elif b_val:
            words_out.append(b_val.split("/")[0].strip())
            evidence.append(f"dictionary_b:full#{tok}")
        elif a_val:
            words_out.append(a_val.split("/")[0].strip())
            evidence.append(f"dictionary_a:full#{tok}")
        else:
            unsupported_terms.append(tok)

    if has_negation:
        words_out.append("na")

    if unsupported_terms:
        # Do NOT invent a plausible-looking word. Leave a visible gap instead.
        nadi_text = None
    else:
        nadi_text = " ".join(words_out) if words_out else None

    return DraftTranslation(subtitle_id, nadi_text, sorted(set(evidence)), assumptions,
                             conflicts, unsupported_terms, rules_used)
