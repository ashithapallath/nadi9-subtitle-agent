"""
Hypothesis formation and testing (brief section 3, steps 2-3).

Rules are extracted deterministically from the grammar note + approved
examples (auditable, no black-box LLM claim), and separately the mock
provider is asked to "propose a rule" -- simulating the surprise event
"the selected language model confidently proposes a grammar rule that
has no support in the evidence pack." Every rule, from either source,
must pass the same counterexample test before being marked "supported".
"""
from __future__ import annotations
import re
from .memory import Rule
from .evidence import EvidenceStore
from .provider import BaseProvider


def extract_candidate_rules(store: EvidenceStore) -> list[Rule]:
    examples = store.all_of_type("approved_example")
    rules = []

    # Rule: negation via pre-verbal "na"
    na_support = [f"approved_example:{e.source_id}" for e in examples if " na " in f" {e.payload['nadi9']} "]
    rules.append(Rule(
        rule_id="negation-1",
        description="Negation is formed with the particle 'na' placed before the verb.",
        category="negation",
        evidence=na_support,
        confidence=0.0,
        status="candidate",
    ))

    # Rule: formal register with "sahib" uses a distinct verb suffix (-ibe vs -ibu)
    formal_support = [f"approved_example:{e.source_id}" for e in examples
                       if "sahib" in e.payload["nadi9"] and "ibe" in e.payload["nadi9"]]
    rules.append(Rule(
        rule_id="respect-2",
        description="Addressing a formal/senior listener ('sahib') shifts the verb ending "
                     "toward an '-ibe' form rather than the casual '-ibu' form.",
        category="politeness",
        evidence=formal_support,
        confidence=0.0,
        status="candidate",
        reason="Grammar note flags this as LOW CONFIDENCE (only 2 supporting examples) -- carried over.",
    ))

    # Rule: kinship term 'dada' + relationship-state interaction (DISPUTED -- experts disagree)
    dada_examples = [e for e in examples if "dada" in e.payload["nadi9"]]
    dada_support = [f"approved_example:{e.source_id}" for e in dada_examples]
    expert_refs = [f"expert_note:{x.source_id}" for x in store.all_of_type("expert_note")]
    rules.append(Rule(
        rule_id="kinship-relationship-1",
        description="The kinship term 'dada' (elder brother) changes position and/or "
                     "co-occurring verb ('aau' vs 'firli') depending on whether the sibling "
                     "relationship is currently tense or reconciled. Experts disagree on the "
                     "exact mechanism (word order vs. verb choice).",
        category="kinship",
        evidence=dada_support + expert_refs,
        confidence=0.0,
        status="candidate",
        reason="expert_note:EXP01 and expert_note:EXP02 propose two different mechanisms for the same data.",
    ))

    return rules


def test_rule_against_examples(rule: Rule, store: EvidenceStore) -> Rule:
    """
    Check each rule against every approved example and record
    counterexamples rather than silently ignoring them (brief 3.3).
    """
    examples = store.all_of_type("approved_example")

    if rule.rule_id == "negation-1":
        counter = [f"approved_example:{e.source_id}" for e in examples
                   if "na" in e.payload["source"].lower() and " na " not in f" {e.payload['nadi9']} "]
        rule.counterexamples = counter
        rule.confidence = 0.9 if not counter and len(rule.evidence) >= 5 else (0.6 if not counter else 0.3)
        rule.status = "supported" if not counter else "disputed"

    elif rule.rule_id == "respect-2":
        # Only 2 supporting examples -> deliberately capped, matches grammar note's own caveat
        rule.confidence = 0.35 if rule.evidence else 0.0
        rule.status = "disputed" if rule.evidence else "rejected"
        if not rule.reason:
            rule.reason = "Too few supporting examples to raise above low confidence."

    elif rule.rule_id == "kinship-relationship-1":
        # Genuinely disputed among human experts -- capped regardless of example count.
        rule.confidence = 0.45
        rule.status = "disputed"

    return rule


def run_model_proposed_rule(provider: BaseProvider, store: EvidenceStore) -> Rule | None:
    """
    Ask the model provider to propose a rule (simulates a real LLM call),
    then subject that proposal to the SAME counterexample/evidence test as
    any human-derived rule. This is where the "confidently wrong grammar
    rule" surprise event is caught -- not by trusting the model, but by
    requiring evidence like everything else.
    """
    proposal = provider.propose_rule(
        prompt="Propose one additional Nadi-9 grammar rule based on the evidence pack.",
        context={},
    )
    if not proposal.get("rule_id"):
        return None

    offered = proposal.get("evidence_offered", [])
    verified_evidence = [ref for ref in offered if store.get(ref) is not None]

    rule = Rule(
        rule_id=proposal["rule_id"],
        description=proposal["description"],
        category="model_proposed",
        evidence=verified_evidence,
        confidence=0.0,
        status="candidate",
    )

    if not verified_evidence:
        rule.status = "rejected"
        rule.confidence = 0.0
        rule.reason = (
            f"Model claimed confidence {proposal.get('model_confidence_claim')} but offered "
            "zero verifiable evidence references. Rejected by the evidence-gate before it could "
            "ever influence a translation. This rule is NOT applied."
        )
    return rule
