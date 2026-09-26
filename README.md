# AI Software Reliability Engineer

A 4-hour buildathon prototype. An AI engineer investigates a failed data pipeline
using real data and execution evidence, not guesswork.

## The problem

Data pipelines often "succeed" while quietly corrupting data. Rows get dropped by a
join, duplicated by a retry, or nulled by a type cast, and the run still reports
`SUCCESS`. Engineers then spend hours comparing source and target, reading logs, and
guessing at causes.

## Prototype concept

One demo journey:

```
Broken customer data pipeline
        ↓
Actual validation evidence      (deterministic pandas checks)
        ↓
AI investigation                (LLM reasons over the evidence)
        ↓
Hypotheses → evidence-based root cause → recommended fix → regression test
```

The validation results are deterministic and the AI analysis is dynamic. No
conclusion is hardcoded. The system does not execute generated code.

The demo scenario is a nightly customer sync that reports `SUCCESS` but has several
injected defects. The target has 23 rows against 20 in the source: 3 customers are
missing, but 5 duplicate rows hide the gap.

## Current backend components

| Path | Purpose |
|---|---|
| `src/data/scenario.py` | Generates the broken pipeline scenario (`python -m src.data.scenario`) and loads it |
| `data/` | `source_customers.csv`, `target_customers.csv`, `pipeline_run.json` (config, steps, logs) |
| `src/validation/tools.py` | Record count, null `customer_id`, duplicate `customer_id`, missing target records, invalid email |
| `src/ai/provider.py` | Minimal LLM provider interface (Anthropic / OpenAI over plain HTTP), set by env vars |
| `src/investigation/models.py` | Structured result: summary, hypotheses, evidence, root cause, fix, regression test |
| `src/investigation/service.py` | Builds the evidence, sends it to the LLM, parses structured JSON output |
| `tests/test_validation.py` | Proves the validation tools work, plus the investigation wiring (stub LLM) |
| `example_usage.py` | How another module calls the investigation service |

### Run

```bash
pip install -r requirements.txt
python -m pytest -q

# LLM configuration (env vars)
LLM_PROVIDER=anthropic   # or openai
LLM_API_KEY=...
LLM_MODEL=...            # optional
python example_usage.py
```

## Intended architecture (React + FastAPI)

The code will be split so that two developers can work in parallel:

```
ai-software-reliability-engineer/
├── frontend/   React + Vite (JavaScript, CSS)          ← Developer 2
│   └── src/{components,pages,services,hooks,types,data}
├── backend/    Python + FastAPI + pandas (+ SQLite)    ← Developer 1
│   ├── app/{api,ai,investigation,validation,models,services,tools,config}
│   ├── data/{source,target}
│   └── tests/
└── docs/       architecture.md, demo-scenario.md
```

The frontend talks to the backend only through a small JSON HTTP API (e.g. scenario,
validation results, investigation result). The existing `src/` modules will move
under `backend/app/` in a later step. They have not been moved yet.

Out of scope: authentication, RBAC, multi-cloud, multiple database connectors, agent
frameworks (LangChain/CrewAI), and a full ETL platform.
