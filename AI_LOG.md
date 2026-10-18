# AI_LOG — AI Development Record

## 1. Development work

- Combined the three task services into one repository with a shared PowerShell startup script and root README.
- Updated Task 1 API startup and environment loading, and improved error handling.
- Switched Task 1 to mock mode for local workflow testing after the configured Anthropic account reported insufficient API credits.
- Updated Task 2 to store human-corrected draft examples and include relevant examples in subsequent Knowledge Brain requests.
- Evaluated the deterministic Task 2 classifier against two synthetic datasets: 50 cases and 20 cases. An initial crash-related classification failure led to a rule update; subsequent runs reported 50/50 and 20/20 exact matches.
- Added Task 3 Knowledge Brain integration and follow-up SOW handling, including scope preservation and tests for persistence and approved-SOW safeguards.
- Expanded the design and evaluation documentation.

## 2. Verified test results

Latest local test runs on 18 October 2026:

| Task | Result |
|---|---:|
| Task 1 — Knowledge Brain | 34 passed |
| Task 2 — Inbox Agent | 10 passed |
| Task 3 — Meeting-to-SOW | 11 passed |
| **Total** | **55 passed** |

Task 1 and Task 3 reported deprecation warnings. These test results verify application behavior covered by the test suites; they do not prove live Claude answer quality.

## 3. Important constraints and decisions

- Genuine Claude generation was not verified because the configured Anthropic account lacked sufficient API credits.
- Mock responses are for local workflow testing, not evidence of model quality.
- Task 2 uses rule-based classification and does not send real email.
- Task 3 uses rule-based transcript extraction. Follow-up scope comparison is text-based, and follow-up tests mock the Knowledge Brain response.
- A genuine comparison of two models for quality, cost, and speed remains outstanding.
- Evaluation results must describe actual runs; missing measurements must not be invented.

## 4. Required AI interaction records

This file is a development summary, not a verbatim record of every AI interaction.

**Complete AI coding-tool chat history:** attach or include the actual exported conversation history from the AI coding tool used during development. Do not reconstruct missing messages from memory and present them as verbatim history.

**Five useful prompts:** select five actual prompts from that history and include their exact wording with a short explanation of the work each supported.

**One rejected AI answer:** identify an actual AI-generated answer that was rejected or materially corrected. Include the original answer, why it was unsuitable, and the correction or decision that followed. If no such example has been documented, record that it still needs to be supplied rather than inventing one.
