import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Authentication — §5 Security Requirements + §6.1 Auth Redirect
// RED-baseline tests: compile but fail until auth is wired up.
// ---------------------------------------------------------------------------

test.describe('Authentication — Unauthenticated Access', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('unauthenticated user visiting / is redirected to login', async ({
    page,
  }) => {
    await page.goto('/');
    // Should redirect to Entra ID login or an app login page
    await expect(page).toHaveURL(/login|authorize/);
  });

  test('unauthenticated user visiting /projects is redirected to login', async ({
    page,
  }) => {
    await page.goto('/projects');
    await expect(page).toHaveURL(/login|authorize/);
  });

  test('unauthenticated user visiting /project/:id is redirected to login', async ({
    page,
  }) => {
    await page.goto('/project/00000000-0000-0000-0000-000000000000');
    await expect(page).toHaveURL(/login|authorize/);
  });

  test('unauthenticated API call returns 401', async ({ request }) => {
    const res = await request.get('/api/projects', {
      headers: { Authorization: '' },
    });
    expect(res.status()).toBe(401);

    const body = await res.json();
    expect(body.error).toMatch(/authentication required/i);
  });
});

test.describe('Authentication — Authenticated Access', () => {
  // These tests assume the default Playwright context has valid auth
  // (e.g., via storageState or global setup that obtains a token).

  test('authenticated user can access the landing page', async ({ page }) => {
    await page.goto('/');
    // Should NOT redirect to login
    await expect(page).not.toHaveURL(/login|authorize/);
    await expect(
      page.getByRole('heading', { name: /onestopagent/i }),
    ).toBeVisible();
  });

  test('authenticated user can access the projects page', async ({ page }) => {
    await page.goto('/projects');
    await expect(page).not.toHaveURL(/login|authorize/);
    await expect(
      page.getByRole('heading', { name: /your projects/i }).or(
        page.getByText(/you haven.t created any projects yet/i),
      ),
    ).toBeVisible();
  });

  test('authenticated user can access a project chat page', async ({
    page,
  }) => {
    // Create a project first
    const res = await page.request.post('/api/projects', {
      data: { description: 'Auth e2e project' },
    });
    const { projectId } = await res.json();

    await page.goto(`/project/${projectId}`);

    await expect(page).not.toHaveURL(/login|authorize/);
    await expect(page.getByTestId('chat-thread')).toBeVisible();
  });

  test('authenticated API call returns 200 for project list', async ({
    request,
  }) => {
    const res = await request.get('/api/projects');
    expect(res.status()).toBe(200);
  });
});
