# Evaluation Report — AI Tech Consultant

## 1. Evaluation approach

This report records measured test and classifier results available during development. Unit/API tests, deterministic classification accuracy, and live language-model quality are different measures and must not be conflated.

The current environment does not have sufficient Anthropic API credits for genuine Claude generation. No LLM quality, cost, or latency comparison is claimed here.

## 2. Task 1 — Knowledge Brain

**Observed test result:** 34 tests passed in the latest previously recorded Task 1 test run, with one warning.

Coverage includes the knowledge API and related retrieval/workflow behavior. The service exposes a `/health` endpoint and `/ask`, plus escalation and feedback endpoints.

**Limitation:** the current mock mode returns a clearly identified test response. Passing tests in mock mode verifies local behavior, not answer accuracy from a live Claude model. A live evaluation using representative questions, source-grounded expected answers, abstention cases, and citation checks remains outstanding.

## 3. Task 2 — Inbox Agent

### Automated tests

**Observed result:** 10 tests passed in the latest previously recorded Task 2 test run. The TypeScript build also completed successfully.

The tests cover API behavior, classification, review/approval safeguards, feedback metrics, correction examples, and the unchanged-draft eligibility logic.

### Synthetic classification datasets

The evaluator calls the local `/classify` endpoint and compares the result with labels in a synthetic dataset. These measurements concern the deterministic classifier only, not generated reply quality.

| Dataset | Cases | Category accuracy | Priority accuracy | Exact-match accuracy |
|---|---:|---:|---:|---:|
| `email_dataset_50.json` | 50 | 100% | 100% | 100% |
| `classification_eval_20.json` | 20 | 100% | 100% | 100% |

The 50-case run initially exposed one missed technical-support example involving an application crash. A crash-related rule was added, the build and tests were rerun, and the subsequent evaluation passed all 50 cases. The separate 20-case evaluation then passed all 20 cases.

These are small synthetic datasets, and the rules were adjusted during development against an observed failure. The results should not be interpreted as unbiased production performance or evidence about hidden evaluation cases.

### Safety limitation

Email approval does not send an email. No production mail provider or real automatic-sending workflow was verified.

## 4. Task 3 — Meeting-to-SOW

**Observed result:** 11 tests passed in the latest recorded run, with two FastAPI deprecation warnings.

The tests cover health, transcript extraction, empty-input validation, SOW creation and retrieval, persistence, approval safeguards, and follow-up behavior including scope comparison.

The follow-up tests mock the Knowledge Brain integration. They verify the local endpoint and persistence behavior, not the correctness of a live knowledge-based feasibility assessment.

The transcript analyzer remains rule-based. Scope comparison uses exact text matching, so it can miss paraphrases and does not constitute semantic change detection.

## 5. Cross-model evaluation status

The assignment calls for at least two models to be compared using numerical measures of quality, cost, and speed. **That comparison is not complete.**

No fabricated model scores, token costs, latency measurements, or live Claude results are reported. A future evaluation should use the same fixed test set for each available model and record:

- Task-specific quality criteria and human review results.
- Citation correctness and unsupported-claim rate for knowledge answers.
- Classification and draft quality for email workflows.
- Scope coverage, omissions, and unsupported commitments for SOWs.
- Latency, retries, and actual API cost where provider usage data is available.

## 6. Reproduction

Run each service's tests using the commands in `README.md`. For Task 2, run `npm run build` before `npm test`.

From the repository root, the 20-case classification evaluation can be run with:

`node .\task2-inbox-agent\scripts\evaluate-classification.js .\task2-inbox-agent\data\classification_eval_20.json`

Run the same script with `.\task2-inbox-agent\data\email_dataset_50.json` to evaluate the 50-case dataset. Results depend on the current classifier implementation and must be regenerated after changes.
