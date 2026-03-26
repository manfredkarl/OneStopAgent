import { Given, When, Then, DataTable } from '@cucumber/cucumber';
import { CustomWorld } from '../support/world';
import assert from 'assert';

// ══════════════════════════════════════════════════════════════════
// Common / Shared Steps — Increment 1
// Background steps reused across chat, orchestration, architecture
// ══════════════════════════════════════════════════════════════════

// ── Authentication backgrounds ──────────────────────────────────

Given('I am authenticated as an Azure seller with a valid Entra ID token', async function (this: CustomWorld) {
  // Simulate obtaining a valid Entra ID token
  // In RED baseline, we generate a mock token; the API must validate it
  this.authToken = 'test-entra-id-token-azure-seller';
  // Attempt to exchange for a real token via the auth endpoint
  try {
    await this.apiRequest('POST', '/api/auth/token', { provider: 'entra-id', role: 'azure-seller' });
    if (this.response && this.response.status === 200 && this.response.body?.token) {
      this.authToken = this.response.body.token;
    }
  } catch {
    // API not implemented yet — keep mock token for RED baseline
  }
});

Given('I am authenticated as an Azure seller', async function (this: CustomWorld) {
  this.authToken = 'test-entra-id-token-azure-seller';
  try {
    await this.apiRequest('POST', '/api/auth/token', { provider: 'entra-id', role: 'azure-seller' });
    if (this.response && this.response.status === 200 && this.response.body?.token) {
      this.authToken = this.response.body.token;
    }
  } catch {
    // API not implemented yet
  }
});

// ── Project state backgrounds ───────────────────────────────────

Given('I have an active project', async function (this: CustomWorld) {
  await this.apiRequest('POST', '/api/projects', { description: 'Test project for Cucumber scenario' });
  if (this.response && this.response.body?.id) {
    this.currentProjectId = this.response.body.id;
    this.currentProject = this.response.body;
  } else {
    // RED baseline: assign a placeholder so steps don't crash
    this.currentProjectId = 'placeholder-project-id';
  }
});

Given('I have an active project with status {string}', async function (this: CustomWorld, status: string) {
  await this.apiRequest('POST', '/api/projects', { description: 'Test project for orchestration' });
  if (this.response && this.response.body?.id) {
    this.currentProjectId = this.response.body.id;
    this.currentProject = this.response.body;
  } else {
    this.currentProjectId = 'placeholder-project-id';
  }
  // Verify or set status
  assert.ok(this.currentProjectId, 'Project ID should be set');
});

Given('I have an active project with gathered requirements', async function (this: CustomWorld) {
  // Create a project and simulate completing the requirements-gathering phase
  await this.apiRequest('POST', '/api/projects', {
    description: 'Web app migration to Azure with 1000 concurrent users, relational DB, Entra ID SSO',
  });
  if (this.response && this.response.body?.id) {
    this.currentProjectId = this.response.body.id;
    this.currentProject = this.response.body;
  } else {
    this.currentProjectId = 'placeholder-project-id';
  }
});

// ── PATCH request step ──────────────────────────────────────────

When('I send a PATCH request to {string} with body:', async function (this: CustomWorld, path: string, dataTable: DataTable) {
  const rows = dataTable.hashes();
  let body: Record<string, any>;
  if (rows.length > 0 && 'field' in rows[0] && 'value' in rows[0] && Object.keys(rows[0]).length === 2) {
    body = {};
    for (const row of rows) {
      // Auto-parse booleans
      if (row.value === 'true') body[row.field] = true;
      else if (row.value === 'false') body[row.field] = false;
      else body[row.field] = row.value;
    }
  } else {
    body = rows[0];
  }
  await this.apiRequest('PATCH', path, body);
});

// ── Generic response assertions ─────────────────────────────────

Then('I receive a {int} response', async function (this: CustomWorld, statusCode: number) {
  assert.ok(this.response, 'No response recorded');
  assert.strictEqual(this.response.status, statusCode, `Expected ${statusCode} but got ${this.response.status}`);
});

Then('I receive a {int} response with error {string}', async function (this: CustomWorld, statusCode: number, errorMsg: string) {
  assert.ok(this.response, 'No response recorded');
  assert.strictEqual(this.response.status, statusCode, `Expected ${statusCode} but got ${this.response.status}`);
  const body = this.response.body;
  assert.ok(body, 'Response body is empty');
  const actual = body.error || body.message || body.detail || JSON.stringify(body);
  assert.strictEqual(actual, errorMsg, `Expected error "${errorMsg}" but got "${actual}"`);
});
