import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Projects List — §6.2
// RED-baseline tests: compile but fail until the UI is implemented.
// ---------------------------------------------------------------------------

/** Helper: create a project via API and return its id. */
async function createProject(
  page: import('@playwright/test').Page,
  description: string,
  customerName?: string,
): Promise<string> {
  const res = await page.request.post('/api/projects', {
    data: { description, customerName },
  });
  const body = await res.json();
  return body.projectId;
}

test.describe('Projects Page', () => {
  // --- Empty State --------------------------------------------------------

  test('shows empty state message when user has no projects', async ({
    page,
  }) => {
    await page.goto('/projects');

    await expect(
      page.getByText(/you haven.t created any projects yet/i),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: /create new project/i }),
    ).toBeVisible();
  });

  test('"Create New Project" link navigates to landing page', async ({
    page,
  }) => {
    await page.goto('/projects');

    await page.getByRole('link', { name: /create new project/i }).click();
    await expect(page).toHaveURL('/');
  });

  // --- With Projects ------------------------------------------------------

  test.describe('with seeded projects', () => {
    test.beforeEach(async ({ page }) => {
      await createProject(page, 'First project description', 'Contoso');
      await createProject(page, 'Second project description', 'Fabrikam');
      await createProject(page, 'Third project without customer');
    });

    test('page header shows "Your Projects"', async ({ page }) => {
      await page.goto('/projects');

      await expect(
        page.getByRole('heading', { name: /your projects/i }),
      ).toBeVisible();
    });

    test('lists all user projects', async ({ page }) => {
      await page.goto('/projects');

      const cards = page.getByTestId('project-card');
      await expect(cards).toHaveCount(3);
    });

    test('each project card shows description (truncated), status badge, and last updated', async ({
      page,
    }) => {
      await page.goto('/projects');

      const card = page.getByTestId('project-card').first();
      await expect(card.getByTestId('project-description')).toBeVisible();
      await expect(card.getByTestId('project-status-badge')).toBeVisible();
      await expect(card.getByText(/ago|just now/i)).toBeVisible();
    });

    test('project card shows customer name when provided', async ({ page }) => {
      await page.goto('/projects');

      await expect(page.getByText('Contoso')).toBeVisible();
      await expect(page.getByText('Fabrikam')).toBeVisible();
    });

    test('project card shows dash for missing customer name', async ({
      page,
    }) => {
      await page.goto('/projects');

      // The third project has no customer name — should show "—"
      const cards = page.getByTestId('project-card');
      const thirdCard = cards.filter({
        hasText: /third project/i,
      });
      await expect(thirdCard.getByText('—')).toBeVisible();
    });

    test('projects are sorted by most recently updated first', async ({
      page,
    }) => {
      await page.goto('/projects');

      const descriptions = await page
        .getByTestId('project-description')
        .allTextContents();

      // Last created should appear first (most recent)
      expect(descriptions[0]).toMatch(/third project/i);
    });

    test('clicking a project card navigates to its chat page', async ({
      page,
    }) => {
      await page.goto('/projects');

      const card = page.getByTestId('project-card').first();
      await card.click();

      await expect(page).toHaveURL(/\/project\/[\w-]+/);
    });

    test('status badge colours match project status', async ({ page }) => {
      await page.goto('/projects');

      const badge = page.getByTestId('project-status-badge').first();
      // Default new project is "in_progress" → expect blue styling
      await expect(badge).toHaveAttribute('data-status', 'in_progress');
    });
  });

  // --- Loading & Error States ---------------------------------------------

  test('shows skeleton rows while projects are loading', async ({ page }) => {
    // Intercept API to delay response and observe skeleton UI
    await page.route('**/api/projects', async (route) => {
      await new Promise((r) => setTimeout(r, 2000));
      await route.continue();
    });

    await page.goto('/projects');

    await expect(page.getByTestId('project-skeleton')).toBeVisible();
  });

  test('shows error state with retry button when API fails', async ({
    page,
  }) => {
    await page.route('**/api/projects', (route) =>
      route.fulfill({ status: 500, body: JSON.stringify({ error: 'fail' }) }),
    );

    await page.goto('/projects');

    await expect(
      page.getByText(/unable to load projects/i),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /retry|try again/i }),
    ).toBeVisible();
  });
});
