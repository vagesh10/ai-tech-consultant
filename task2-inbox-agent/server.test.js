
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const testDirectory = fs.mkdtempSync(
  path.join(os.tmpdir(), "inbox-agent-test-")
);

process.env.INBOX_DB_PATH = path.join(testDirectory, "test.db");
process.env.PORT = "0";

const { app, db } = require("./dist/server");

let server;
let baseUrl;

before(async () => {
  server = app.listen(0, "127.0.0.1");

  await new Promise((resolve, reject) => {
    server.once("listening", resolve);
    server.once("error", reject);
  });

  baseUrl = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  if (server) {
    await new Promise((resolve) => server.close(resolve));
  }

  db.close();
  fs.rmSync(testDirectory, { recursive: true, force: true });
});

async function createEmail(subject, body) {
  const response = await fetch(`${baseUrl}/emails`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject, body }),
  });

  assert.equal(response.status, 201);
  return (await response.json()).email;
}

test("health endpoint reports healthy status", async () => {
  const response = await fetch(`${baseUrl}/health`);
  assert.equal(response.status, 200);

  const result = await response.json();
  assert.equal(result.status, "ok");
});

test("classifies urgent billing emails", async () => {
  const response = await fetch(`${baseUrl}/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subject: "Urgent invoice issue",
      body: "Please check my billing immediately.",
    }),
  });

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    category: "billing",
    priority: "high",
  });
});

test("creates an email pending human review", async () => {
  const email = await createEmail(
    "Test email",
    "Please help me with my website."
  );

  assert.ok(email.id > 0);
  assert.equal(email.status, "pending_review");
  assert.equal(email.subject, "Test email");
});

test("saves feedback and updates metrics", async () => {
  const email = await createEmail(
    "Feedback test",
    "Please review this question."
  );

  const feedbackResponse = await fetch(
    `${baseUrl}/emails/${email.id}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rating: "positive",
        comment: "Helpful",
      }),
    }
  );

  assert.equal(feedbackResponse.status, 201);

  const metricsResponse = await fetch(`${baseUrl}/metrics`);
  const metrics = await metricsResponse.json();

  assert.equal(metrics.totalEmails, 2);
  assert.equal(metrics.feedback.total, 1);
  assert.equal(metrics.feedback.positive, 1);
});

test("approves a draft without sending an email", async () => {
  const email = await createEmail(
    "Approval test",
    "Please review this draft."
  );

  const response = await fetch(
    `${baseUrl}/emails/${email.id}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewNote: "Approved in test",
      }),
    }
  );

  assert.equal(response.status, 200);

  const result = await response.json();
  assert.equal(result.email.status, "approved");
  assert.match(result.message, /No email was sent/i);
});

test("rejects a draft and saves the review note", async () => {
  const email = await createEmail(
    "Rejection test",
    "Please review this draft."
  );

  const response = await fetch(
    `${baseUrl}/emails/${email.id}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewNote: "Rejected in test",
      }),
    }
  );

  assert.equal(response.status, 200);

  const result = await response.json();
  assert.equal(result.email.status, "rejected");
  assert.equal(result.email.reviewNote, "Rejected in test");
});


test("enables category eligibility after 20 unchanged approvals and revokes it after negative feedback", async () => {
  let category;

  // Approve 20 unchanged drafts of the same category.
  for (let i = 0; i < 20; i++) {
    const email = await createEmail(
      "Urgent invoice issue",
      "Please check my billing immediately."
    );

    category = email.category;

    const response = await fetch(
      `${baseUrl}/emails/${email.id}/approve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      }
    );

    assert.equal(response.status, 200);

    const result = await response.json();
    assert.equal(result.draftUnchanged, true);
  }

  let response = await fetch(`${baseUrl}/categories/eligibility`);
  let result = await response.json();

  assert.equal(result.requiredConsecutiveUnchangedDrafts, 20);

  let categoryQuality = result.categories.find(
    (item) => item.category === category
  );

  assert.ok(categoryQuality, "Expected category quality record");
  assert.equal(categoryQuality.consecutiveUnchanged, 20);
  assert.equal(categoryQuality.autoSendEligible, 1);

  // Negative feedback must revoke category eligibility.
  const email = await createEmail(
    "Urgent invoice issue",
    "My billing issue still needs help."
  );

  response = await fetch(
    `${baseUrl}/emails/${email.id}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rating: "negative",
        comment: "The draft needs improvement.",
      }),
    }
  );

  assert.equal(response.status, 201);

  response = await fetch(`${baseUrl}/categories/eligibility`);
  result = await response.json();

  categoryQuality = result.categories.find(
    (item) => item.category === category
  );

  assert.equal(categoryQuality.consecutiveUnchanged, 0);
  assert.equal(categoryQuality.autoSendEligible, 0);
  assert.equal(result.automaticSendingEnabled, false);
});

test("an edited draft resets the consecutive unchanged approval sequence", async () => {
  const firstEmail = await createEmail(
    "Urgent invoice issue",
    "Please check my billing immediately."
  );

  const category = firstEmail.category;

  // First unchanged approval: counter becomes 1.
  let response = await fetch(
    `${baseUrl}/emails/${firstEmail.id}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }
  );

  assert.equal(response.status, 200);

  // Create and edit another draft in the same category.
  const editedEmail = await createEmail(
    "Urgent invoice issue",
    "Please check another billing question."
  );

  response = await fetch(
    `${baseUrl}/emails/${editedEmail.id}/draft`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draftReply: "I reviewed your question and need more details.",
      }),
    }
  );

  assert.equal(response.status, 200);

  // Approving the edited draft must reset the sequence.
  response = await fetch(
    `${baseUrl}/emails/${editedEmail.id}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }
  );

  assert.equal(response.status, 200);

  const eligibilityResponse = await fetch(
    `${baseUrl}/categories/eligibility`
  );

  const eligibility = await eligibilityResponse.json();
  const quality = eligibility.categories.find(
    (item) => item.category === category
  );

  assert.equal(quality.consecutiveUnchanged, 0);
  assert.equal(quality.autoSendEligible, 0);
});


test("stores and retrieves a human-corrected draft as a learning example", async () => {
  const email = await createEmail(
    "Invoice billing issue",
    "Please help me understand my invoice payment."
  );

  const correctedDraft =
    "Thank you for contacting us about your invoice. We will review the payment details and follow up with you.";

  const editResponse = await fetch(
    `${baseUrl}/emails/${email.id}/draft`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ draftReply: correctedDraft }),
    }
  );

  assert.equal(editResponse.status, 200);

  const learningResponse = await fetch(
    `${baseUrl}/learning/examples?category=billing`
  );

  assert.equal(learningResponse.status, 200);

  const learning = await learningResponse.json();
  const example = learning.examples.find(
    (item) => item.emailId === email.id
  );

  assert.ok(example, "Expected the human correction to be saved");
  assert.equal(example.category, "billing");
  assert.equal(example.correctedDraft, correctedDraft);
  assert.ok(example.originalDraft.length > 0);
});

test("includes human-corrected examples in the next Knowledge Brain request", async () => {
  // Save the original fetch so the test can restore it.
  const originalFetch = global.fetch;
  const capturedRequests = [];

  try {
    // Intercept only Knowledge Brain requests.
    global.fetch = async (url, options) => {
      if (String(url).endsWith("/ask")) {
        capturedRequests.push(JSON.parse(options.body));

        return new Response(
          JSON.stringify({
            answer: "Mock support answer",
            sources: [],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      }

      return originalFetch(url, options);
    };

    // First email: create a draft and correct it as a human.
    const firstEmail = await createEmail(
      "Invoice billing issue",
      "Please explain my invoice payment."
    );

    const correctedDraft =
      "Thank you for contacting us. We will review your invoice details.";

    let response = await fetch(
      `${baseUrl}/emails/${firstEmail.id}/draft`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draftReply: correctedDraft }),
      }
    );

    assert.equal(response.status, 200);

    // Second email in the same category should use the correction.
    await createEmail(
      "Another invoice billing issue",
      "Please explain this invoice charge."
    );

    assert.equal(capturedRequests.length, 2);

    const nextQuestion = capturedRequests[1].question;

    assert.ok(
      nextQuestion.includes("Human-reviewed writing examples"),
      "Expected learning guidance in the Knowledge Brain request"
    );

    assert.ok(
      nextQuestion.includes(correctedDraft),
      "Expected the human-corrected draft in the next request"
    );
  } finally {
    global.fetch = originalFetch;
  }
});
