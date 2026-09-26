"""Test-only LLM boundary doubles. Never imported by production code."""

import copy
import json


def valid_llm_output(**overrides):
    """A schema-valid LLM reply. Content is placeholder text; tests assert on structure, not meaning."""
    out = {
        "summary": "stub summary",
        "observed_facts": ["[validation.duplicate_customer_id] stub fact"],
        "hypotheses": [
            {"hypothesis": "h1", "status": "SUPPORTED", "evidence": ["[validation.duplicate_customer_id] e1"],
             "reasoning": "r1"},
            {"hypothesis": "h2", "status": "REJECTED", "evidence": ["[pipeline.execution_summary] e2"],
             "reasoning": "r2"},
            {"hypothesis": "h3", "status": "INCONCLUSIVE", "evidence": [], "reasoning": "r3"},
        ],
        "root_cause_status": "IDENTIFIED",
        "root_cause": "stub root cause",
        "root_cause_evidence": ["[validation.duplicate_customer_id] rc evidence"],
        "root_cause_reasoning": "stub reasoning",
        "recommended_fix": "stub fix",
        "regression_test": {"name": "test_x", "description": "desc", "code": "def test_x(): pass"},
    }
    out = copy.deepcopy(out)
    out.update(overrides)
    return out


class StubProvider:
    """Records every prompt; returns each reply in turn (last one repeats)."""

    def __init__(self, *replies):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in (replies or [valid_llm_output()])]
        self.prompts, self.systems = [], []

    def complete(self, system, user):
        self.systems.append(system)
        self.prompts.append(user)
        return self.replies[min(len(self.prompts) - 1, len(self.replies) - 1)]

    def context(self, i=0):
        """The JSON evidence package sent in call i."""
        return json.loads(self.prompts[i].split("\n\n", 1)[1])


class FailingProvider:
    def __init__(self, exc):
        self.exc = exc

    def complete(self, system, user):
        raise self.exc
