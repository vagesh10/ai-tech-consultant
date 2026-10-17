# AI_LOG — Development Notes

## Implemented and verified

- Unified three existing services under a root project with a shared PowerShell startup script and root README.
- Preserved copies of the original task repositories outside the unified root repository before removing nested Git metadata from the active task folders.
- Task 1: adjusted API startup/environment loading and improved `/ask` error handling. The configured Anthropic account reported insufficient API credits, so mock mode is used for local workflow testing.
- Task 2: added/verified correction-example retrieval and inclusion in subsequent Knowledge Brain requests; expanded tests for review safeguards and learning behavior.
- Task 2: evaluated a 50-case synthetic email dataset and a separate 20-case classification dataset. A missed crash-related technical-support case led to a classifier rule update. Subsequent runs reported 50/50 and 20/20 exact matches.
- Task 3: implemented the Knowledge Brain request helper and a follow-up SOW endpoint. Added tests for follow-up scope comparison, persistence, unknown SOWs, and protection of approved SOWs.
- Latest recorded Task 3 test run: 11 passed, with two FastAPI deprecation warnings.

## Current constraints

- Genuine Claude generation could not be verified because the Anthropic account has insufficient credits.
- Task 1 mock answers are not model-quality evidence.
- Task 2 uses rule-based classification and does not send real email.
- Task 3 uses rule-based transcript extraction and exact-text scope comparison. Its follow-up tests mock Task 1.
- Cross-model quality, cost, and speed comparisons are pending.
- Documentation and test counts should be refreshed after subsequent code changes.

This file records development facts and observed outcomes; it is not a verbatim AI chat log.
