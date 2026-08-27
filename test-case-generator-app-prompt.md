# Development Prompt: AI-Powered Test Case Generator App

## Role & Objective

You are a senior full-stack architect and QA automation expert. Design and build a web application called **"Spec2QA"** that takes a user story (or requirement/feature description) as input and automatically generates:

1. **Extensive manual test cases** (structured, human-readable, execution-ready)
2. **Automated test scripts** (framework-based, execution-ready code)
3. **A traceability matrix** linking every acceptance criterion to its test cases

The app should behave like an experienced QA lead: thorough, detail-oriented, and capable of thinking through positive, negative, edge, boundary, security, performance, and accessibility scenarios — not just the "happy path."

---

## 1. Input Specification

The app must accept a **Story** in one or more of these formats:

- **Free-text user story**: `"As a [role], I want [feature], so that [benefit]"`
- **Story + Acceptance Criteria**: plain text or Gherkin (`Given/When/Then`)
- **Structured JIRA/Azure DevOps import**: title, description, acceptance criteria, labels, priority, linked epics
- **Pasted requirement documents** (PRD excerpts, BRD sections)
- **File upload**: `.docx`, `.pdf`, `.csv`, `.xlsx`, or `.txt`

Input fields to capture:
| Field | Required | Notes |
|---|---|---|
| Story Title | Yes | |
| Story Description | Yes | |
| Acceptance Criteria | Recommended | Improves accuracy; auto-inferred if missing |
| Application Type | Optional | Web, Mobile, API, Desktop — affects test types generated |
| Tech Stack / UI Framework | Optional | Helps tailor automated script syntax (e.g., React selectors) |
| Priority / Risk Level | Optional | Influences depth of edge-case coverage |
| Existing Test Repository Link | Optional | For duplicate detection and traceability |

If acceptance criteria are missing or vague, the app should **first generate clarifying acceptance criteria** and present them for user confirmation before generating test cases — never silently assume.

---

## 2. Core Functional Requirements

### 2.1 Story Analysis Engine
- Parse the story to extract: actors/roles, actions, preconditions, business rules, data entities, and expected outcomes.
- Detect ambiguity or missing information (e.g., undefined error states, missing field constraints) and flag it as "Clarification Needed" items alongside the output.
- Classify the story by type (UI feature, API endpoint, business logic, integration, data migration, etc.) to tailor test case categories.

### 2.2 Manual Test Case Generation
For each story, generate a full suite covering:
- **Positive/functional** scenarios (happy path, all acceptance criteria)
- **Negative** scenarios (invalid input, unauthorized access, error handling)
- **Boundary value** scenarios (min/max lengths, numeric limits, date ranges)
- **Edge cases** (empty states, concurrent actions, network interruption, timeouts)
- **Security** scenarios (auth/authz, input sanitization, injection, data exposure) where applicable
- **Performance/load** considerations (flagged as candidates for perf testing, not full load tests)
- **Accessibility** checks (keyboard navigation, screen reader labels, contrast) for UI stories
- **Cross-browser / cross-device** variations for web/mobile stories
- **Regression impact** notes (related existing features that could be affected)

Each manual test case must include:
```
Test Case ID: TC-[STORY-ID]-[SEQ]
Title:
Category: (Functional / Negative / Boundary / Security / Accessibility / etc.)
Priority: (Critical / High / Medium / Low)
Preconditions:
Test Data:
Steps: (numbered, atomic, unambiguous)
Expected Result:
Actual Result: (blank, filled during execution)
Status: (Not Run / Pass / Fail / Blocked)
Linked Acceptance Criteria: (traceability ID)
```

### 2.3 Automated Test Script Generation
- Convert selected manual test cases into automation-ready scripts.
- Support multiple frameworks, selectable by the user:
  - **Web UI**: Playwright, Selenium (Java/Python), Cypress
  - **API**: Postman/Newman collections, RestAssured, pytest + requests
  - **Mobile**: Appium
  - **BDD style**: Cucumber/Gherkin feature files with step definitions
- Generated scripts must include:
  - Descriptive test names matching the manual test case ID
  - Setup/teardown (fixtures, test data seeding)
  - Assertions matching the "Expected Result" of the manual case
  - Comments linking back to the acceptance criteria
  - Placeholder locators/selectors clearly marked (`// TODO: update selector`) when exact UI structure is unknown
- Provide a downloadable, ready-to-run project scaffold (folder structure, config file, sample `.env`, README) — not just isolated snippets.

### 2.4 Traceability & Coverage
- Auto-generate a **Requirement Traceability Matrix (RTM)**: Acceptance Criteria ↔ Manual Test Cases ↔ Automated Scripts ↔ Execution Status.
- Show a coverage summary (e.g., "18 test cases generated, covering 6/6 acceptance criteria, 4 flagged for automation").
- Detect and merge duplicate/overlapping test cases across multiple stories in the same project.

### 2.5 Execution & Reporting
- Allow manual testers to execute test cases in-app: mark Pass/Fail/Blocked, attach screenshots/logs, add comments.
- Allow triggering automated scripts directly (local runner or CI/CD webhook — Jenkins, GitHub Actions, GitLab CI, Azure Pipelines).
- Aggregate results into a dashboard: pass/fail rate, flaky test detection, execution time trends, defect linkage.
- Auto-file bug reports (with repro steps pulled from the failed test case) to Jira/Azure DevOps via integration.

### 2.6 Export & Integration
- Export manual test cases as Excel/CSV, PDF, or push directly to TestRail, Zephyr, Xray, or Azure Test Plans.
- Export automation scripts as a zipped project or push to a connected Git repository via pull request.
- Two-way sync option with Jira/Azure DevOps for story import and status updates.

---

## 3. Non-Functional Requirements
- **Accuracy over volume**: prioritize meaningful, non-redundant test cases over inflated counts.
- **Explainability**: every generated test case should be traceable to a specific part of the story or acceptance criteria.
- **Editability**: all generated content (manual cases and scripts) must be fully editable in-app before export/execution.
- **Versioning**: track changes to test cases as the underlying story evolves; flag outdated test cases when a story is edited.
- **Multi-user collaboration**: role-based access (QA lead, tester, developer, viewer), comments, and review/approval workflow before test cases are marked "ready for execution."
- **Auditability**: full history of who generated/edited/executed each test case and when.
- **Scalability**: support batch input of multiple stories (e.g., a whole sprint backlog) in one run.
- **Data privacy**: no story or test data should be used to train external models without explicit org-level consent; support on-prem/private deployment for sensitive data.

---

## 4. Suggested Architecture
- **Frontend**: React (or Vue) SPA — story input form, test case editor (spreadsheet-like grid), RTM viewer, execution dashboard.
- **Backend**: Node.js/Python (FastAPI) API layer handling parsing, generation orchestration, integrations, and auth.
- **Generation Layer**: LLM-based reasoning engine (via Anthropic API) for story parsing, test case drafting, and script generation, with deterministic templating for structured output formatting.
- **Storage**: PostgreSQL for structured data (stories, test cases, RTM, execution history); object storage (S3-compatible) for attachments/screenshots.
- **Integrations Layer**: connectors for Jira, Azure DevOps, TestRail/Xray/Zephyr, GitHub/GitLab, CI/CD webhooks.
- **Execution Runner**: containerized sandbox (Docker) to run generated automation scripts on demand or via CI trigger.

---

## 5. Sample Input → Output Flow (for validation during development)

**Input Story**:
> As a registered user, I want to reset my password via email, so that I can regain access to my account if I forget it.
> Acceptance Criteria: User receives reset link within 2 minutes; link expires in 24 hours; new password must meet complexity rules.

**Expected Output**:
- 15–25 manual test cases spanning: valid reset flow, expired link, reused link, invalid email format, unregistered email, weak password rejection, rate-limiting of reset requests, email delivery failure handling, concurrent reset requests, accessibility of the reset form.
- Automated Playwright + API-level scripts for the top critical-path and negative scenarios.
- RTM showing all 3 acceptance criteria mapped to at least one test case each.

---

## 6. Deliverables Expected From This Build
1. Working web app matching the above functional scope (MVP: manual test case generation + export; Phase 2: automation script generation + execution + integrations).
2. API documentation for the generation and execution endpoints.
3. Sample generated output (as above) for at least 3 different story types (UI feature, API feature, data-validation rule).
4. Admin config screen for selecting default automation framework, integration credentials, and org-level generation preferences (e.g., max test cases per story, required categories).

---

## 7. Success Criteria
- A QA engineer can go from a raw user story to a reviewed, execution-ready manual test suite in under 5 minutes.
- Generated automated scripts run with ≤10% manual edit required for locator/selector updates.
- 100% of acceptance criteria are traceable to at least one generated test case.
- False-positive/irrelevant test case rate (as judged by a human reviewer) is under 10%.
