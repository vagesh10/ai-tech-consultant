# Design — AI Tech Consultant

## 1. Purpose and design goals

AI Tech Consultant combines three services into one technical consulting workflow:

1. **Knowledge Brain:** retrieves information from Brilliant Directories support documentation and provides source-aware answers, escalation, and feedback endpoints.
2. **Inbox Agent:** classifies incoming emails, requests context from Knowledge Brain, creates draft replies, and supports human review and feedback.
3. **Meeting-to-SOW:** analyzes meeting transcripts, creates draft Statements of Work (SOWs), checks relevant product documentation through Knowledge Brain, and supports follow-up updates and approval.

The services remain separate applications with explicit HTTP API boundaries. Tasks 2 and 3 reuse Task 1 rather than maintaining separate copies of the support knowledge base.

The primary design goals are modularity, traceability, human oversight, and honest handling of uncertainty. The current implementation is a working prototype, not a fully autonomous production system.

## 2. Architecture and technology choices

### 2.1 Knowledge Brain — Task 1

**Technology:** Python, FastAPI, Sentence Transformers, ChromaDB, SQLite, and the Anthropic API integration.

Knowledge Brain is the shared support-information service. Its ingestion workflow uses the Brilliant Directories support sitemap and associated article content. Sentence Transformer embeddings and ChromaDB support retrieval, while source metadata helps connect retrieved content to the original documentation.

The service also provides workflows for escalation and feedback. These allow questions requiring additional expertise to be tracked rather than forcing the system to invent an answer.

The main API surface includes:

- `GET /health` — service health.
- `POST /ask` — request a knowledge-based answer.
- Escalation endpoints — create, retrieve, and update escalation records.
- Feedback endpoints — record and retrieve feedback.

The intended answer flow is to receive a question, retrieve relevant source material, generate or construct a response, and return supporting source information. When evidence is insufficient, the service should abstain rather than present an unsupported product claim.

**Runtime limitation:** mock mode is enabled in the current development environment because the configured Anthropic account lacks sufficient API credits. Mock responses allow local integration testing, but they are not genuine Claude-generated answers and cannot establish answer quality.

### 2.2 Inbox Agent — Task 2

**Technology:** TypeScript, Node.js, Express, SQLite, and the TypeScript compiler.

Inbox Agent handles incoming email records and provides classification, draft management, review, feedback, metrics, and learning-example endpoints. TypeScript is compiled into `dist/` for the test and production-style start commands.

The current classifier uses deterministic text rules to assign an email category and priority. This makes the classification behavior predictable and easy to test, but it does not provide semantic understanding equivalent to a trained or language-model classifier.

For drafting, Task 2 requests supporting context from Knowledge Brain and stores the result with the email record. The human reviewer can edit the draft, approve it, or reject it. Corrections are stored as learning examples and can be included in later requests as style guidance.

The implementation includes tests for the unchanged-draft approval sequence and for resetting that sequence after negative feedback or an edit. The threshold logic is not equivalent to an operational automatic-sending capability.

**Safety boundary:** no real email-sending provider is configured. Approval records a review decision; it does not send an email. Automatic sending remains disabled.

### 2.3 Meeting-to-SOW — Task 3

**Technology:** Python, FastAPI, and SQLite.

Meeting-to-SOW accepts meeting transcripts and produces draft SOW records. The current transcript analyzer uses rules and keywords to identify candidate scope, deliverables, assumptions, exclusions, and open questions.

The main endpoints include:

- `GET /health` — service health.
- `POST /analyze` — analyze transcript content.
- `POST /sow/generate` — create a draft SOW.
- `GET /sow/{sow_id}` — retrieve a stored SOW.
- `POST /sow/{sow_id}/follow-up` — update a pending SOW using a follow-up transcript.
- `POST /sow/{sow_id}/approve` — record human approval.

The service requests product-documentation context from Task 1 before treating product feasibility as verified. If the knowledge service is unavailable, abstains, or returns a recognized mock response, feasibility is not treated as confirmed.

Follow-up processing preserves existing scope while incorporating newly extracted information. It returns a comparison that includes newly detected scope items. The current comparison is based on extracted text, not semantic interpretation. It does not reliably detect all removals or equivalent statements expressed in different words.

All generated SOWs require human review. The current analyzer is rule-based; a complete multi-agent transcript-analysis pipeline and comprehensive developer task estimates have not been implemented.

## 3. Service integration and data flows

### 3.1 Email workflow

1. An email subject and body are submitted to Inbox Agent.
2. Deterministic rules assign a category and priority.
3. Task 2 calls Knowledge Brain's `/ask` endpoint for relevant context.
4. The response and source information are used when preparing the draft.
5. The email and draft are stored for review.
6. A reviewer can edit, approve, or reject the draft.
7. Corrections and feedback are retained for subsequent style guidance and workflow metrics.

The knowledge request is an integration boundary: Task 2 depends on Task 1 being reachable for live retrieval. A mock response can verify that requests and responses flow through the services, but it cannot verify the factual correctness of the generated answer.

### 3.2 Meeting-to-SOW workflow

1. A transcript is submitted to Meeting-to-SOW.
2. Rule-based analysis extracts candidate scope and related SOW sections.
3. Task 3 sends a product-related question to Knowledge Brain.
4. The response is assessed for whether feasibility can be treated as verified.
5. A draft SOW is persisted with a review-required status.
6. A follow-up transcript can update a pending draft while preserving previously recorded scope.
7. The service returns the updated SOW and a text-based change summary.
8. A human reviews the SOW and may approve it.

The workflow separates product-documentation lookup from transcript analysis. It does not assume that a retrieved support article proves that every proposed customization is feasible.

### 3.3 Cross-service communication

Task 1 exposes the shared knowledge API on port `8000`. Task 2 runs on port `3001`, and Task 3 runs on port `8002`. Local configuration determines the Knowledge Brain URL used by the dependent services.

HTTP requests keep the applications independently testable. Each task can be tested directly, while integration tests can replace or mock dependencies to verify request construction, response handling, and failure behavior.

The local startup script launches the three services from the repository root. The health endpoints provide a simple way to verify that the processes are responding.

## 4. Data persistence and state

SQLite is used for workflow records in the dependent services and for supporting application records where configured. Task 1 also maintains a local vector index for retrieval.

The persistence responsibilities are different:

- **Knowledge Brain:** support retrieval data, source metadata, escalation records, and feedback.
- **Inbox Agent:** email records, classification and priority, draft content, review outcomes, metrics, and learning examples.
- **Meeting-to-SOW:** SOW records, extracted sections, transcript history, review status, and update information.

Local databases and generated vector indexes are runtime artifacts. They should not be confused with source code or assumed to be portable without their associated data and configuration.

The repository excludes local environments, generated caches, environment files, and local database artifacts through `.gitignore`, while selected evaluation datasets and reports are retained as project files.

## 5. Reliability, security, and human oversight

The system uses the following design principles:

- **Secrets:** API keys belong in local environment files and must not be committed to version control.
- **Source grounding:** knowledge answers should include source information where available.
- **Abstention:** missing evidence should remain uncertainty rather than being converted into a confident product claim.
- **Human approval:** email handling and SOW approval retain review steps.
- **Safe integration:** provider errors and unavailable services must not be presented as verified product knowledge.
- **Traceability:** workflow records and evaluation reports should make it possible to inspect outcomes.
- **Honest reporting:** mock-mode checks, deterministic classifier results, and live model evaluations are different forms of evidence and must be reported separately.

The current prototype has important boundaries. Real email delivery is not configured. Live Claude answer quality has not been evaluated in the current mock-mode environment. Rule-based extraction can miss context and relationships that require deeper interpretation. These limitations should be considered before any production deployment.

## 6. Testing and evaluation approach

The project includes automated tests for each service. Task 1 tests cover its API and knowledge workflow behavior. Task 2 tests cover classification, draft review, feedback, learning-example storage, and integration behavior. Task 3 tests cover transcript analysis, SOW operations, and follow-up behavior.

The local classification evaluator also measures category and priority predictions against labeled synthetic email datasets. Those results describe the tested deterministic classifier and dataset only. They do not demonstrate the quality of generated email replies or establish superiority over another language model.

A full evaluation should separately measure task-level correctness, integration behavior, failure handling, latency, and cost. Any comparison between models must use the same evaluation cases and record actual measured outcomes. No unrun model comparison should be reported as completed.

## 7. Local operation

From the repository root, run:

`.\start-all.ps1`

The expected local service ports are `8000`, `3001`, and `8002`. Health-check URLs and individual test commands are documented in `README.md`.

Each service can also be tested independently from its own task directory. Task 2 must be built before running tests that import the compiled output.

## 8. Known gaps and future work

The current implementation is a prototype with working APIs and basic service integration. It is not yet a fully verified autonomous multi-agent system.

The principal gaps are:

1. Live Claude generation and quality evaluation are blocked in the current environment by insufficient API credits.
2. Inbox classification currently uses deterministic rules rather than a model-based classification system.
3. Email delivery is not integrated, and automatic sending remains disabled.
4. Meeting transcript analysis uses rules rather than a complete multi-agent pipeline.
5. SOW developer task breakdowns and effort estimates need a more complete, validated implementation.
6. Follow-up comparison relies on extracted text and does not reliably identify semantic changes or explicit removals.
7. Comparative model evaluation must be run and documented with actual quality, latency, and cost measurements.

These gaps define the next engineering steps. They should not be described as completed capabilities until implemented and tested.
