# Evaluation Report — AI Tech Consultant

## 1. Evaluation approach

This report separates automated tests, deterministic classifier evaluations, and live language-model quality measurements. These are different forms of evidence and must not be treated as interchangeable.

Tests were rerun locally on 18 October 2026. The results below are the observed outputs of those runs. The current development environment does not have sufficient Anthropic API credits for genuine Claude generation, so no live Claude quality, cost, or latency result is claimed.

## 2. Task 1 — Knowledge Brain

**Latest observed test result: 34 passed, 0 failed.**

Command:

`python -m pytest tests -q`

The run completed in 21.03 seconds and reported one ChromaDB-related deprecation warning.

The existing tests cover API health, answer retrieval, relevant and unrelated queries, citation validation, abstention, escalation creation and resolution, ingestion, and semantic search behavior.

These tests verify local application behavior. Several answer-generation tests use a fake Claude client, and the API tests can use mock mode. They do not establish the factual accuracy of live Claude responses.

**Outstanding evaluation:** a dedicated set of at least 20 labeled knowledge-question cases with expected evidence, citation checks, abstention cases, and measured outcomes. A live model evaluation remains blocked by API credits.

## 3. Task 2 — Inbox Agent

### Automated tests

**Latest observed result: 10 passed, 0 failed.**

Commands:

`npm run build`

`npm test`

The TypeScript build completed successfully. The test run completed in approximately 4.27 seconds.

The tests cover service health, classification, draft creation, feedback metrics, approval without email delivery, rejection, unchanged-draft eligibility, reset behavior after edits or negative feedback, correction-example persistence, and inclusion of corrections in subsequent Knowledge Brain requests.

### Synthetic classification evaluation

The local evaluator compares the deterministic classifier against labeled synthetic email datasets.

| Dataset | Cases | Category accuracy | Priority accuracy | Exact-match accuracy |
|---|---:|---:|---:|---:|
| `email_dataset_50.json` | 50 | 100% | 100% | 100% |
| `classification_eval_20.json` | 20 | 100% | 100% | 100% |

The 50-case evaluation initially exposed one missed technical-support example involving an application crash. A crash-related rule was added, followed by a successful build and test run. The subsequent 50-case and 20-case evaluations reported no mismatches.

These results are limited to the supplied synthetic datasets. Because the classifier rules were adjusted after an observed failure, the results should not be interpreted as unbiased production performance or evidence of performance on hidden cases. They measure classification, not draft-reply quality.

**Safety limitation:** approval does not send an email. A real email provider and automatic delivery workflow have not been verified.

## 4. Task 3 — Meeting-to-SOW

**Latest observed test result: 11 passed, 0 failed.**

Command:

`python -m pytest tests -q`

The run completed in 1.48 seconds and reported two FastAPI lifecycle deprecation warnings.

The tests cover health checks, transcript analysis, empty-input validation, SOW generation and retrieval, persistence across application startup, approval safeguards, follow-up scope changes, transcript-history preservation, and rejection of follow-ups to approved SOWs.

The follow-up tests mock the Knowledge Brain feasibility response. They verify local integration and persistence behavior, not the factual correctness of a live product-feasibility assessment.

The analyzer remains rule-based, and follow-up comparison relies on extracted text rather than semantic understanding.

**Outstanding evaluation:** at least 20 labeled transcript cases with expected scope, deliverables, assumptions, exclusions, open questions, and follow-up changes. The current test suite is not equivalent to that dedicated evaluation.

## 5. Combined test summary

| Task | Latest observed result | Warnings |
|---|---:|---:|
| Task 1 — Knowledge Brain | 34 passed, 0 failed | 1 |
| Task 2 — Inbox Agent | 10 passed, 0 failed | 0 |
| Task 3 — Meeting-to-SOW | 11 passed, 0 failed | 2 |
| **Total** | **55 passed, 0 failed** | **3** |

These counts describe the latest recorded automated test runs. They do not represent 55 independent labeled quality-evaluation cases.

## 6. Cross-model evaluation status

**Status: incomplete.**

The assignment requires comparison of at least two models using numerical quality, cost, and speed measures. That comparison has not been completed.

No fabricated model scores, API costs, token counts, latency measurements, or live Claude results are reported.

A future comparison should use the same fixed evaluation cases for each model and record:

- Task 1: answer correctness, citation validity, source support, and unsupported-claim or abstention behavior.
- Task 2: classification performance and human-reviewed draft quality.
- Task 3: scope coverage, omitted requirements, unsupported commitments, and follow-up change detection.
- Operational measures: latency, retries, and actual API cost when available.

## 7. Reproduction

Run the automated tests from the repository root:

**Task 1**

`Set-Location .\task1-knowledge-brain; python -m pytest tests -q; Set-Location ..`

**Task 2**

`Set-Location .\task2-inbox-agent; npm run build; npm test; Set-Location ..`

**Task 3**

`Set-Location .\task3-meeting-to-sow; python -m pytest tests -q; Set-Location ..`

The classification evaluator can be run from the repository root:

`node .\task2-inbox-agent\scripts\evaluate-classification.js .\task2-inbox-agent\data\classification_eval_20.json`

For the 50-case dataset, use:

`node .\task2-inbox-agent\scripts\evaluate-classification.js .\task2-inbox-agent\data\email_dataset_50.json`

Regenerate the classification reports after classifier changes. Results may differ if the implementation or datasets change.

## 8. Remaining work

The main outstanding evaluation work is to create and run dedicated labeled evaluation sets for Tasks 1 and 3, evaluate email-draft quality separately from classification, and perform a genuine two-model comparison if model access and budget become available.

The prototype also retains implementation limitations documented in `DESIGN.md`: mock-mode knowledge responses, rule-based email classification and transcript extraction, no real email delivery, and incomplete semantic scope comparison.
