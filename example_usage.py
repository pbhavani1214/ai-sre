"""How another module calls the investigation service.

    set LLM_PROVIDER=anthropic   (or openai)
    set LLM_API_KEY=...
    python example_usage.py
"""

import json

from src.investigation.service import investigate_scenario
from src.validation.suite import run_demo_validation_suite

# 1. Deterministic evidence (no LLM involved) - the same suite behind GET /api/demo/scenario.
suite = run_demo_validation_suite()
for r in suite["results"]:
    print(f"[{r['status']}] {r['name']} ({r['severity']}): {r['summary']}")

# 2. Dynamic AI analysis over that evidence (same path as POST /api/investigate with use_demo_data=true).
result = investigate_scenario()

print("\nROOT CAUSE:", result.root_cause)
print(json.dumps(result.to_dict(), indent=2))
