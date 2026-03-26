import { Given, When, Then } from '@cucumber/cucumber';
import { CustomWorld } from '../support/world';
import assert from 'assert';

// ══════════════════════════════════════════════════════════════════
// Authentication & Security Steps — Increment 1
// Steps for auth enforcement (401/403/429) from chat.feature
// ══════════════════════════════════════════════════════════════════

// ── Given steps ─────────────────────────────────────────────────

Given('my JWT token has expired', async function (this: CustomWorld) {
  // Craft an expired JWT (header.payload with exp in the past, fake signature)
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({
    sub: 'test-azure-seller',
    role: 'azure-seller',
    iat: Math.floor(Date.now() / 1000) - 7200,
    exp: Math.floor(Date.now() / 1000) - 3600, // expired 1 hour ago
  })).toString('base64url');
  const signature = 'invalid-expired-signature';
  this.authToken = `${header}.${payload}.${signature}`;
});

Given('I have made {int} requests within the last minute', async function (this: CustomWorld, count: number) {
  // Exhaust the rate limit by making N rapid requests
  this.requestCount = count;
  for (let i = 0; i < count; i++) {
    try {
      await this.apiRequest('GET', '/api/projects');
    } catch {
      // Some requests may fail — that's expected
    }
  }
});

// ── When steps ──────────────────────────────────────────────────

When('I send a POST request to {string} without a Bearer token', async function (this: CustomWorld, path: string) {
  this.skipAuth = true;
  const savedToken = this.authToken;
  const savedCookies = [...this.cookies];
  this.authToken = null;
  this.cookies = [];
  await this.apiRequest('POST', path, { description: 'Test project without auth' });
  this.skipAuth = false;
  // Don't restore auth — leave it unauthenticated for Then step
});

When('I send another request to any API endpoint', async function (this: CustomWorld) {
  await this.apiRequest('GET', '/api/projects');
});

// ── Then steps ──────────────────────────────────────────────────

Then('the response includes a WWW-Authenticate header {string}', async function (this: CustomWorld, expectedValue: string) {
  assert.ok(this.response, 'No response recorded');
  const wwwAuth = this.response.headers.get('www-authenticate');
  assert.ok(wwwAuth, 'Expected WWW-Authenticate header');
  assert.strictEqual(wwwAuth, expectedValue, `Expected WWW-Authenticate "${expectedValue}" but got "${wwwAuth}"`);
});

Then('the response includes a Retry-After header', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const retryAfter = this.response.headers.get('retry-after');
  assert.ok(retryAfter, 'Expected Retry-After header');
  const seconds = parseInt(retryAfter, 10);
  assert.ok(!isNaN(seconds) && seconds > 0, `Retry-After should be a positive integer, got "${retryAfter}"`);
});
