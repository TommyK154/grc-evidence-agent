# Evaluation results

Run: 2026-06-18 23:40:51 UTC

## Aggregate

- micro precision: 0.56
- micro recall: 0.82
- exact match: 4/10

## Per-control

| control | TP | FP | FN | precision | recall | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| CC6.1 | 2 | 0 | 1 | 1.00 | 0.67 | recall miss |
| CC6.2 | 0 | 0 | 0 | 1.00 | 1.00 | match (correct empty) |
| CC6.3 | 0 | 1 | 0 | 0.00 | 1.00 | precision miss (over-mapped) |
| CC6.6 | 1 | 1 | 0 | 0.50 | 1.00 | precision miss |
| CC6.7 | 1 | 0 | 0 | 1.00 | 1.00 | exact match |
| CC6.8 | 2 | 0 | 0 | 1.00 | 1.00 | exact match |
| CC7.1 | 1 | 1 | 1 | 0.50 | 0.50 | mixed |
| CC7.2 | 1 | 0 | 0 | 1.00 | 1.00 | exact match |
| CC7.3 | 0 | 3 | 0 | 0.00 | 1.00 | precision miss (over-mapped) |
| CC8.1 | 1 | 1 | 0 | 0.50 | 1.00 | precision miss |

## Misses

### CC6.1

- verdict: recall miss
- false positives (FP): none
- false negatives (FN): aws.root_mfa.123456789012

### CC6.3

- verdict: precision miss (over-mapped)
- false positives (FP): github.required_reviews.main
- false negatives (FN): none

### CC6.6

- verdict: precision miss
- false positives (FP): github.two_factor_status.TommyK154
- false negatives (FN): none

### CC7.1

- verdict: mixed
- false positives (FP): github.dependabot_alerts.grc-evidence-agent
- false negatives (FN): github.dependabot_status.grc-evidence-agent

### CC7.3

- verdict: precision miss (over-mapped)
- false positives (FP): aws.cloudtrail_enabled.123456789012, github.dependabot_status.grc-evidence-agent, github.secret_scanning.grc-evidence-agent
- false negatives (FN): none

### CC8.1

- verdict: precision miss
- false positives (FP): github.required_reviews.main
- false negatives (FN): none
