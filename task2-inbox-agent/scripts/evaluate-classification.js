const fs = require("node:fs");
const path = require("node:path");

const baseUrl = process.env.INBOX_AGENT_URL || "http://127.0.0.1:3001";
const dataPath = process.argv[2] || path.join(__dirname, "..", "data", "email_dataset_50.json");
const cases = JSON.parse(fs.readFileSync(dataPath, "utf8"));

async function main() {
  let categoryCorrect = 0;
  let priorityCorrect = 0;
  let bothCorrect = 0;
  const failures = [];

  for (const item of cases) {
    const response = await fetch(`${baseUrl}/classify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject: item.subject, body: item.body }),
    });

    if (!response.ok) {
      throw new Error(`API returned HTTP ${response.status} for ${item.id}`);
    }

    const actual = await response.json();
    const categoryOK = actual.category === item.expectedCategory;
    const priorityOK = actual.priority === item.expectedPriority;
    if (categoryOK) categoryCorrect++;
    if (priorityOK) priorityCorrect++;
    if (categoryOK && priorityOK) bothCorrect++;

    if (!categoryOK || !priorityOK) {
      failures.push({
        id: item.id,
        subject: item.subject,
        expected: { category: item.expectedCategory, priority: item.expectedPriority },
        actual,
      });
    }
  }

  const pct = (n) => `${((n / cases.length) * 100).toFixed(1)}%`;
  const report = {
    dataset: path.basename(dataPath),
    totalCases: cases.length,
    categoryAccuracy: pct(categoryCorrect),
    priorityAccuracy: pct(priorityCorrect),
    exactMatchAccuracy: pct(bothCorrect),
    passed: bothCorrect,
    failed: cases.length - bothCorrect,
    failures,
    note: "These are measured classifier results for the current /classify endpoint, not LLM draft-quality or model-comparison results.",
  };

  console.log(JSON.stringify(report, null, 2));
  const outputPath = path.join(process.cwd(), "classification-eval-results.json");
  fs.writeFileSync(outputPath, JSON.stringify(report, null, 2) + "\n", "utf8");
  console.log(`\nSaved report: ${outputPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
