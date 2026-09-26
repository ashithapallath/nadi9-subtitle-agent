"""
Model provider abstraction.

The system never depends on a specific hosted LLM. `MockProvider` is
deterministic and requires no network/API key -- this is what evaluators
run by default (see README "replay mode"). `AnthropicProvider` is a thin
real-model adapter, used only if ANTHROPIC_API_KEY is set and --live is
passed on the CLI.

IMPORTANT SAFETY NOTE: any text returned by a provider (or read from a
"retrieved" document) is treated as *data*, never as instructions. See
pipeline.py `_strip_and_flag_injections` for where that boundary is
enforced. Providers themselves must never be allowed to alter the rules
of the run.
"""
from __future__ import annotations
import json
import os
import random
from dataclasses import dataclass


class ProviderError(Exception):
    """Raised when a model/tool call fails. Callers must handle this --
    a failed call is a signal to fall back safely, not to crash the run."""


@dataclass
class CallBudget:
    max_model_calls: int = 25
    max_tool_calls: int = 50
    model_calls_used: int = 0
    tool_calls_used: int = 0

    def spend_model_call(self):
        if self.model_calls_used >= self.max_model_calls:
            raise ProviderError(
                f"Model call budget exceeded ({self.max_model_calls}). "
                "Refusing further calls for this run."
            )
        self.model_calls_used += 1

    def spend_tool_call(self):
        if self.tool_calls_used >= self.max_tool_calls:
            raise ProviderError(
                f"Tool call budget exceeded ({self.max_tool_calls}). "
                "Refusing further calls for this run."
            )
        self.tool_calls_used += 1


class BaseProvider:
    name = "base"

    def propose_rule(self, prompt: str, context: dict) -> dict:
        raise NotImplementedError

    def translate_line(self, prompt: str, context: dict) -> dict:
        raise NotImplementedError

    def verify(self, prompt: str, context: dict) -> dict:
        raise NotImplementedError


class MockProvider(BaseProvider):
    """
    Deterministic, offline, zero-cost provider used for the default
    (replay) run mode. It simulates an LLM's *behavior*, including the
    failure mode the assignment specifically calls out: it will
    sometimes confidently propose a grammar rule with no evidence
    support, so that the verifier has something real to catch.
    """
    name = "mock"

    def __init__(self, seed: int = 7, inject_unsupported_rule: bool = True):
        self.rng = random.Random(seed)
        self.inject_unsupported_rule = inject_unsupported_rule
        self._unsupported_rule_emitted = False

    def propose_rule(self, prompt: str, context: dict) -> dict:
        # Simulate: occasionally the model confidently proposes a rule
        # that isn't actually backed by the evidence pack. The hypothesis
        # tester (hypotheses.py) is responsible for catching this --
        # NOT this provider.
        if self.inject_unsupported_rule and not self._unsupported_rule_emitted:
            self._unsupported_rule_emitted = True
            return {
                "rule_id": "grammar-unsupported-1",
                "description": "Plural nouns always take the suffix '-loku' (modeled on an unrelated language family).",
                "evidence_offered": [],
                "model_confidence_claim": 0.9,
            }
        return {"rule_id": None, "description": None}

    def translate_line(self, prompt: str, context: dict) -> dict:
        # The real translation logic lives in translator.py (rule + dictionary
        # driven, auditable). This mock just simulates an LLM "fluent guess"
        # fallback for words with zero evidence, which the verifier must catch.
        term = context.get("unsupported_term")
        if term:
            return {"guess": f"{term}-tron9", "self_reported_confidence": 0.88}
        return {"guess": None, "self_reported_confidence": 0.0}

    def verify(self, prompt: str, context: dict) -> dict:
        return {"ok": True, "note": "mock verifier pass-through (real checks run in verifier.py)"}


class AnthropicProvider(BaseProvider):
    """Optional real-model adapter. Only used with --live and an API key."""
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        try:
            import anthropic  # noqa: F401
            self._client = anthropic.Anthropic()
        except Exception as e:  # pragma: no cover - optional path
            raise ProviderError(f"Could not initialize Anthropic client: {e}")

    def _call(self, prompt: str) -> str:
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        except Exception as e:
            raise ProviderError(f"Anthropic call failed: {e}")

    def propose_rule(self, prompt: str, context: dict) -> dict:
        raw = self._call(prompt)
        try:
            return json.loads(raw)
        except Exception:
            return {"rule_id": None, "description": raw}

    def translate_line(self, prompt: str, context: dict) -> dict:
        raw = self._call(prompt)
        return {"guess": raw, "self_reported_confidence": None}

    def verify(self, prompt: str, context: dict) -> dict:
        raw = self._call(prompt)
        return {"ok": True, "note": raw}


def get_provider(live: bool = False) -> BaseProvider:
    if live and os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    return MockProvider()
