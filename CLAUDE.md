measured eval harness. Python + Anthropic API. v1 scope: 10 controls,
2 evidence sources, nothing auto-accepts.
 
## Architecture
- `controls.yaml` - 10 SOC 2 CC-series controls with expected evidence types
- `collectors/github_collector.py` - live GitHub API (branch protection,
  required reviews, 2FA status, Dependabot, secret scanning) via fine-grained
  PAT from env
- `collectors/aws_mock_collector.py` - reads `data/sample_aws_config.json`
  into the same Evidence schema (mock keeps the demo reproducible)
- `agent/mapper.py` - Claude API maps evidence to controls; structured JSON
  {control_id, evidence_ids[], confidence, rationale}; validate, retry once
  on malformed output
- `agent/prompts.py` - versioned prompt templates only; no inline prompts
  elsewhere
- `approve.py` - human approval queue; results land in review_queue.json +
  REVIEW.md as `pending` until a human approves. Never auto-accept.
- `evals/golden.yaml` - hand-labeled ground truth (authored by Tommy, never
  generated)
- `evals/run_evals.py` - precision/recall per control vs golden set, printed
  and written to evals/results.md
## Hard rules
- Secrets live in `.env` only (gitignored, chmod 600). Load via
  python-dotenv. Never print, log, or commit a secret. `.env.example`
  documents required keys.
- Never write to `evals/golden.yaml`. It is human-authored ground truth.
- Nothing auto-accepts a mapping. The approval queue is a design principle,
  not a placeholder.
- All deps go in requirements.txt. Stack is anthropic, requests, pyyaml,
  python-dotenv. Ask before adding more.
- Type hints and docstrings on every public function.
## Workflow
- Work on feature branches; merge to main via PR (branch protection is on).
- Commit messages tell the build story: `area: what and why`,
  e.g. `prompts: tighten mapping criteria after CC6.1 misses`.
- Run from repo root with the venv active: `source .venv/bin/activate`.
- Evidence schema everywhere: {id, source, type, raw, collected_at}.
- CC7.3 has no satisfiable evidence in v1 by design; correct agent behavior
  is no mapping. Do not "fix" this.