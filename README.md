# grc-evidence-agent

A measured eval harness for an agentic GRC workflow: it collects compliance
evidence, asks Claude to propose which evidence satisfies which SOC 2 control,
and routes every proposal to a human before anything is accepted.

## The idea

The agent reads a set of SOC 2 common-criteria controls, collects evidence from
a live GitHub repository and a mock AWS configuration, and asks Claude to propose
control mappings. Each proposal carries a confidence rating (high, medium, or
low) and a one-line rationale. Nothing is accepted automatically: every proposal
lands in a human approval queue as `pending` and only a person can approve it.
The point of the project is to measure how well the agent maps evidence, and in
particular whether it knows when to stay silent, against a hand-authored answer
key.

## Quickstart

Requires Python 3.10+ (the code uses `from __future__ import annotations` and
modern type-hint syntax).

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt        # or: pip install -r requirements.lock

# 3. Create your .env from the template, then fill it in
cp .env.example .env
chmod 600 .env
```

`.env` holds four values (see `.env.example`):

```
ANTHROPIC_API_KEY=    # for the mapper
GITHUB_PAT=           # fine-grained PAT for the GitHub collector
GITHUB_OWNER=         # default target owner (or pass --owner)
GITHUB_REPO=          # default target repo  (or pass --repo)
```

The `.env` file is gitignored. Never print, log, or commit a secret.

### GitHub PAT scope

The collector uses a fine-grained personal access token. Grant it:

- **Contents: read** (repository metadata, branch rulesets, Dependabot
  enablement, secret-scanning status)
- **Administration: read** (classic branch protection and required reviews)

**Dependabot alerts: read is intentionally left off.** With that permission
absent, the call to the Dependabot alerts endpoint returns a 403. The collector
captures the 403 in the evidence payload and treats it as a non-signal (neither
proof the control is present nor proof it is absent) rather than as a finding.
This is deliberate: it exercises the agent's handling of undeterminable results.

### Run the pipeline

```bash
# owner/repo from the CLI...
python run.py --owner your-org --repo your-repo

# ...or fall back to GITHUB_OWNER / GITHUB_REPO from .env
python run.py
```

This collects evidence, asks the mapper to propose mappings, writes the proposals
to the approval queue as `pending`, and prints a run summary. Review the
proposals in `REVIEW.md`, then approve individually:

```bash
python approve.py list
python approve.py approve CC6.1 --reviewer your-name
```

### Score against the golden set

```bash
python -m evals.run_evals
```

This compares the agent's proposals to the hand-authored ground truth and writes
`evals/results.md`. Run `run.py` first: the eval reads the proposals it produces
and exits non-zero if they are missing.

## How it works

The pipeline is one pass, orchestrated by `run.py`:

```
collectors  ->  evidence inventory  ->  mapper  ->  proposals  ->  approval queue  ->  REVIEW.md
 (GitHub +       (evidence_             (Claude,    (agent_         (review_            (human-
  mock AWS)       inventory.json)        per         mappings        queue.json,         readable)
                                         control)    .json)          pending)
```

1. **Collect.** `collectors/github_collector.py` pulls live signals (branch
   protection, required reviews, org 2FA, Dependabot status, Dependabot alerts,
   secret scanning). `collectors/aws_mock_collector.py` reads
   `data/sample_aws_config.json` (IAM password policy, CloudTrail, S3 public
   access block, root MFA). The mock keeps the AWS half reproducible without live
   credentials. Both emit the same evidence schema and never auto-judge: a 403, a
   404, or a disabled state is recorded verbatim in `raw` for a human to audit.
2. **Inventory.** The combined evidence is written to `evidence_inventory.json`,
   the lookup that later resolves any evidence id back to its source, type, raw
   content, and collection time.
3. **Map.** `agent/mapper.py` calls Claude once per control, supplying that
   control's definition and the full evidence list, and validates the structured
   JSON response (`{control_id, evidence_ids, confidence, rationale}`), retrying
   once on malformed output. The raw proposals are written to
   `evals/agent_mappings.json`.
4. **Queue.** `approve.py` enqueues every proposal as `pending` in
   `review_queue.json` and renders `REVIEW.md`. A proposal becomes `approved`
   only through `approve.py`, and nowhere else.

Separately, `evals/run_evals.py` scores `evals/agent_mappings.json` against
`evals/golden.yaml` by deterministic set comparison. It is plain Python: no
Anthropic call, no import from `agent/`. No model judges a model.

### Module map

| Path | Role |
| --- | --- |
| `run.py` | End-to-end orchestrator (collect, inventory, map, enqueue). |
| `evidence.py` | The shared `Evidence` schema: `{id, source, type, raw, collected_at}`. |
| `controls.yaml` | 10 SOC 2 controls and their expected evidence types. |
| `collectors/github_collector.py` | Live GitHub API collector. |
| `collectors/aws_mock_collector.py` | Mock AWS collector reading the sample config. |
| `agent/mapper.py` | Claude-backed evidence-to-control mapper. |
| `agent/prompts.py` | Versioned prompt templates (the only place prompt text lives). |
| `approve.py` | Human approval queue and `REVIEW.md` renderer. |
| `evals/golden.yaml` | Hand-authored ground truth (never written by code). |
| `evals/run_evals.py` | Precision/recall scorer vs the golden set. |
| `evals/results.md` | Durable, committed record of the latest scored run. |

## The evaluation

The golden set in `evals/golden.yaml` is the answer key. It is:

- **Hand-authored.** Each control's expected evidence and the reasoning behind it
  are written by a person, not generated.
- **Frozen.** A project rule forbids any code from writing to it; the eval reads
  it and nothing else does.
- **Never derived from agent output.** The labels reflect independent GRC
  judgment against the actual collected evidence, not the model's proposals.
- **Read only by the eval harness.** The mapper never imports or sees the golden
  set, so it is never part of any prompt.

The scorer compares the agent's evidence ids to the golden ids per control and
reports:

- **Micro-averaged precision and recall.** True positives, false positives, and
  false negatives are summed across all controls before dividing, so each cited
  piece of evidence counts equally.
- **Exact match, X/10.** The number of controls where the agent's set equals the
  golden set exactly.
- **Zero-denominator rules.** When both the golden set and the agent propose
  nothing, that counts as correct restraint (precision 1.0, recall 1.0). When the
  golden set is empty but the agent proposes something, every proposed item is a
  false positive (precision 0.0). When the golden set is non-empty but the agent
  proposes nothing, it is a pure recall miss (recall 0.0).

## Design decisions

### The CC7.3 restraint failure, before and after

The eval exists to catch the failure that matters most in compliance:
**over-crediting** (a precision problem), not just missed evidence (a recall
problem). A false "you are covered" is more dangerous than a visible gap.

**CC7.3 is deliberately uncoverable.** The control asks for evaluation of
security events: a process, a workflow, records of events being assessed and
acted on. None of the v1 collectors produce that. Every collected item is a
configured feature or a state, not a process. So the correct answer for CC7.3 is
an empty mapping, and the golden set records exactly that.

**First run (V1 prompt).** The agent mapped three monitoring signals to CC7.3.
In its own rationale it called them detection inputs rather than evidence of an
evaluation process, and then mapped them anyway. Across all ten controls the run
scored precision 0.56, recall 0.82, with 7 false positives and 2 false
negatives. Every one of those 7 false positives had been predicted by the design
of the golden set: the traps worked.

**The fix.** One general restraint instruction added to the system prompt (V2).
It names no control id and no evidence id, so it cannot overfit to CC7.3. It
tells the agent to abstain when nothing genuinely satisfies a control, never to
cite a non-signal (a 403, a 404, or a not-applicable status), and never to credit
a mechanism that enforces nothing (for example a required-review rule that
requires zero approvals).

**Second run (V2 prompt).** Precision rose from 0.56 to 1.00. The CC7.3 trap
cleared to an empty mapping. All 7 false positives were gone.

**The honest cost.** Recall fell from 0.82 to 0.55. The blunt restraint language
also suppressed some valid configured-state evidence. CC8.1 dropped to 0.00
recall because the agent proposed nothing at all there, discarding the valid
branch-protection mapping along with the toothless zero-approval review rule it
was right to reject.

**The thesis.** The system moved from failing unsafe (a false "you are covered")
to failing safe (a miss that the human approval queue is there to catch). A false
positive is worse than a false negative, because it manufactures unearned
assurance.

### Other decisions

- **Human-in-the-loop is a principle, not a placeholder.** `approve.py` is the
  single enforcement point for "nothing auto-accepts": `approved` status is
  reachable only through an explicit human approval. A fresh run re-queues
  proposals as `pending` and carries a prior approval forward only when the
  re-proposed mapping cites the same evidence (order-insensitive) with the same
  confidence and rationale.
- **The golden set is independent and frozen.** It is hand-authored, never
  written by code, and never seen by the mapper, so the score is a fair test
  rather than a model grading itself.
- **Evidence provenance lives in `REVIEW.md`.** Each cited evidence id resolves
  to its source, type, raw collector note, and collection timestamp, so any
  proposed claim traces back to the raw signal a reviewer can inspect.
- **Prompts are versioned.** All prompt text lives in `agent/prompts.py`.
  `MAPPING_SYSTEM_V1` is retained for rollback and review, `MAPPING_SYSTEM_V2` is
  active, and `PROMPT_VERSION` is bumped accordingly.
- **Non-determinism is acknowledged.** Proposals regenerate on each run. The
  durable record is the committed `evals/results.md`, and the before/after story
  is the git transition between the V1 and V2 runs.

## Results

Current run, scored against the golden set with the V2 prompt
(from `evals/results.md`):

**Aggregate**

- micro precision: 1.00
- micro recall: 0.55
- exact match: 6/10

**Per-control**

| control | TP | FP | FN | precision | recall | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| CC6.1 | 1 | 0 | 2 | 1.00 | 0.33 | recall miss |
| CC6.2 | 0 | 0 | 0 | 1.00 | 1.00 | match (correct empty) |
| CC6.3 | 0 | 0 | 0 | 1.00 | 1.00 | match (correct empty) |
| CC6.6 | 1 | 0 | 0 | 1.00 | 1.00 | exact match |
| CC6.7 | 1 | 0 | 0 | 1.00 | 1.00 | exact match |
| CC6.8 | 1 | 0 | 1 | 1.00 | 0.50 | recall miss |
| CC7.1 | 1 | 0 | 1 | 1.00 | 0.50 | recall miss |
| CC7.2 | 1 | 0 | 0 | 1.00 | 1.00 | exact match |
| CC7.3 | 0 | 0 | 0 | 1.00 | 1.00 | match (correct empty) |
| CC8.1 | 0 | 0 | 1 | 1.00 | 0.00 | recall miss |

**Both runs side by side**

| metric | V1 (first run) | V2 (current run) |
| --- | --- | --- |
| micro precision | 0.56 | 1.00 |
| micro recall | 0.82 | 0.55 |
| exact match | 4/10 | 6/10 |
| false positives | 7 | 0 |
| false negatives | 2 | 5 |

The V1 figures are not in the working tree; they are the recorded numbers from
the first scored run. The shift is the whole point: the agent moved from failing
unsafe (a false "you are covered") to failing safe (a miss the human approval
queue is there to catch).

## Scope and limitations

This project was built to explore agentic GRC patterns, not as a product. v1
covers:

- 10 SOC 2 common-criteria controls (`controls.yaml`).
- 2 evidence sources: a live GitHub collector and a mock AWS config collector.
- Human-approval-only flow: nothing auto-accepts.

A bounded claim about behavior, limited to the runs inspected here: across those
runs the agent did not invent evidence, and every evidence id it cited resolved
to a real collected signal. Its failure mode was over-crediting relative to
strict, hand-authored ground truth, not fabrication. Nothing in the code
structurally prevents fabrication. The defense is provenance: every cited id is
resolved in `REVIEW.md` back to the raw collector output, so a claim that does
not trace to a real signal is visible to a reviewer.

CC7.3 has no satisfiable evidence in v1 by design; the correct agent behavior is
no mapping, and that is not a bug to fix.

## Repository layout

```
grc-evidence-agent/
├── run.py                          # end-to-end orchestrator
├── evidence.py                     # shared Evidence schema
├── controls.yaml                   # 10 SOC 2 controls + expected evidence types
├── approve.py                      # human approval queue + REVIEW.md renderer
├── agent/
│   ├── mapper.py                   # Claude-backed evidence-to-control mapper
│   └── prompts.py                  # versioned prompt templates
├── collectors/
│   ├── github_collector.py         # live GitHub API collector
│   └── aws_mock_collector.py       # mock AWS collector
├── data/
│   └── sample_aws_config.json      # mock AWS evidence source
├── evals/
│   ├── golden.yaml                 # hand-authored ground truth (read-only)
│   ├── run_evals.py                # precision/recall scorer
│   └── results.md                  # durable record of the latest run
├── .env.example                    # required env keys (copy to .env)
├── requirements.txt                # top-level dependencies
└── requirements.lock               # pinned dependency versions
```

Generated at runtime and gitignored: `evidence_inventory.json`,
`evals/agent_mappings.json`, `review_queue.json`, `REVIEW.md`.

## Built with

Solo-authored. Claude Code was used as a tool during development.
