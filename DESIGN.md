# Design — AI Tech Consultant

## 1. Purpose

AI Tech Consultant combines three services that support a customer-facing technical consulting workflow:

1. Knowledge Brain — searches support documentation and exposes answers, citations, abstention, escalation, and feedback APIs.
2. Inbox Agent — classifies incoming emails, requests knowledge-based context, drafts replies, and supports human review and feedback.
3. Meeting-to-SOW — extracts potential project scope from meeting transcripts and creates reviewable Statements of Work (SOWs).

The services are separate applications connected through HTTP APIs. The intended design is to reuse Task 1 knowledge retrieval rather than independently maintain support knowledge in Tasks 2 and 3.

## 2. Service architecture

### Task 1: Knowledge Brain

- Language: Python.
- Web framework: FastAPI.
- Knowledge retrieval: Sentence Transformers embeddings, ChromaDB, and support-article retrieval.
- Persistence: local application database for supporting workflows such as escalations and feedback.
- API: `/health`, `/ask`, escalation endpoints, and feedback endpoints.

The ingestion workflow reads the Brilliant Directories support sitemap and associated article content. The implementation includes retrieval, source metadata, and mechanisms intended to support synchronization and source-grounded answers.

Answers should cite supplied sources. When the evidence is insufficient, the service should abstain instead of inventing product capabilities. Questions requiring an expert can enter an escalation workflow.

**Important runtime limitation:** local mock mode is enabled in the current development environment because the configured Anthropic account has insufficient API credits. Mock responses are useful for API and workflow testing but are not evidence of genuine Claude answer quality.

### Task 2: Inbox Agent

- Language: TypeScript.
- Runtime and framework: Node.js and Express.
- Persistence: SQLite.
- Build: TypeScript compiled to `dist/`.
- API: health, classification, email drafting and retrieval, draft updates, approval/rejection, feedback, metrics, and learning-example endpoints.

The current classifier uses deterministic text rules to assign categories and priority. The email workflow requests supporting context from Task 1 and stores drafts for review. Human corrections are retained as learning examples and can be supplied as style guidance for subsequent requests.

Approval is deliberately not connected to a real email-sending provider. The application must not be described as sending emails automatically. The 20-unchanged-draft rule and feedback-reset behavior are exercised by tests, but actual automatic sending remains disabled.

### Task 3: Meeting-to-SOW

- Language: Python.
- Framework: FastAPI.
- Persistence: SQLite.
- Main components: transcript analyzer, SOW storage, Knowledge Brain HTTP client, follow-up endpoint, and approval endpoint.

The current analyzer uses rules and keywords to extract candidate scope, deliverables, assumptions, exclusions, and open questions. SOWs are stored as drafts requiring human review.

The `/sow/generate` endpoint creates a draft, `/sow/{sow_id}` retrieves it, `/sow/{sow_id}/follow-up` updates a pending draft, and `/sow/{sow_id}/approve` records approval. The follow-up endpoint compares extracted scope strings and returns added and removed items. Exact-text comparison is not semantic understanding and can miss equivalent wording.

Task 3 calls Task 1 `/ask` to request support-documentation context before finalizing a draft. If Task 1 is unavailable, abstains, or returns a recognized mock answer, feasibility is not treated as verified.

## 3. Main data flows

### Email workflow

1. An email enters Task 2.
2. Rule-based classification assigns category and priority.
3. Task 2 requests relevant context from Task 1.
4. A draft is stored and presented for human review.
5. A reviewer can edit, approve, or reject the draft.
6. Corrections and feedback can be used as future style guidance.

### Meeting workflow

1. A transcript enters Task 3.
2. Rule-based extraction produces candidate scope and related SOW sections.
3. Task 3 asks Task 1 for relevant support documentation.
4. The SOW is saved as `pending_review`.
5. A follow-up transcript can update a pending draft and return a scope comparison.
6. A human reviewer approves the SOW.

## 4. Reliability and safety

- Keep secrets in local environment files; never commit API keys.
- Keep generated databases, vector indexes, virtual environments, and Node dependencies out of Git.
- Validate request payloads and return appropriate HTTP errors.
- Preserve human review for SOW approval and email handling.
- Treat unavailable knowledge services and insufficient evidence as unknown, not proof that a feature is impossible.
- Do not invent product capabilities, prices, effort, or delivery dates.
- Distinguish mocked integration tests from live provider tests.
- Report only measured evaluation results.

## 5. Running locally

From the repository root, run `.\start-all.ps1`. The services are configured for ports 8000, 3001, and 8002. See `README.md` for test commands.

## 6. Known gaps

The current implementation is not a fully verified autonomous multi-agent system. Task 2 uses a rule-based classifier, Task 3 uses rule-based transcript extraction, and real Claude generation is blocked by account credits in the current environment. Real email sending is not configured. Follow-up transcript history, semantic change detection, comprehensive developer task estimates, and comparative LLM evaluation require further work.
