import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from src.evidence import load_evidence
from src.memory import RunMemory
from src.hypotheses import extract_candidate_rules, test_rule_against_examples
import json


DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture
def store():
    return load_evidence(DATA_DIR)


@pytest.fixture
def memory_with_rules(store):
    m = RunMemory()
    for rule in extract_candidate_rules(store):
        test_rule_against_examples(rule, store)
        m.add_rule(rule)
    return m


@pytest.fixture
def episode():
    return json.loads((DATA_DIR / "episode.json").read_text())
