"""How another module calls the investigation service.

    set LLM_PROVIDER=anthropic   (or openai)
    set LLM_API_KEY=...
    python example_usage.py
"""

import json

from src.data.scenario import PIPELINE_DESCRIPTION, load_scenario
from src.investigation.service import investigate
from src.validation.tools import run_all_validations

source_df, target_df, pipeline_run = load_scenario()

# 1. Deterministic evidence (no LLM involved).
validation_results = run_all_validations(source_df, target_df)
for v in validation_results:
    print(f"[{'PASS' if v.passed else 'FAIL'}] {v.check}: {v.summary}")

# 2. Dynamic AI analysis over that evidence.
result = investigate(
    pipeline_description=PIPELINE_DESCRIPTION,
    source=source_df,
    target=target_df,
    execution_evidence=pipeline_run,
    validation_results=validation_results,
)

print("\nROOT CAUSE:", result.root_cause)
print(json.dumps(result.to_dict(), indent=2))
