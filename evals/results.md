# Evaluation results

Run: 2026-06-26 05:03:28 UTC

## Aggregate

- micro precision: 1.00
- micro recall: 0.55
- exact match: 6/10

## Per-control

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

## Misses

### CC6.1

- verdict: recall miss
- false positives (FP): none
- false negatives (FN): aws.root_mfa.123456789012, github.branch_protection.main

### CC6.8

- verdict: recall miss
- false positives (FP): none
- false negatives (FN): github.secret_scanning.grc-evidence-agent

### CC7.1

- verdict: recall miss
- false positives (FP): none
- false negatives (FN): github.dependabot_status.grc-evidence-agent

### CC8.1

- verdict: recall miss
- false positives (FP): none
- false negatives (FN): github.branch_protection.main
