import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Landing Page — §6.1
// RED-baseline tests: these compile but will fail until the UI is implemented.
// ---------------------------------------------------------------------------

test.describe('Landing Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  // --- Branding -----------------------------------------------------------

  test('renders OneStopAgent branding and logo', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /onestopagent/i }),
    ).toBeVisible();
    await expect(page.getByAltText(/onestopagent logo/i)).toBeVisible();
  });

  // --- Create Project Form ------------------------------------------------

  test('shows create project form with description field and submit button', async ({
    page,
  }) => {
    const descriptionInput = page.getByPlaceholder(
      /describe your customer.*scenario/i,
    );
    await expect(descriptionInput).toBeVisible();

    const createButton = page.getByRole('button', { name: /create project/i });
    await expect(createButton).toBeVisible();
  });

  test('Create Project button is disabled when description is empty', async ({
    page,
  }) => {
    const createButton = page.getByRole('button', { name: /create project/i });
    await expect(createButton).toBeDisabled();
  });

  test('Create Project button becomes enabled after typing a description', async ({
    page,
  }) => {
    const descriptionInput = page.getByPlaceholder(
      /describe your customer.*scenario/i,
    );
    await descriptionInput.fill('Migrate legacy CRM to Azure');

    const createButton = page.getByRole('button', { name: /create project/i });
    await expect(createButton).toBeEnabled();
  });

  test('shows optional customer name input', async ({ page }) => {
    const customerNameInput = page.getByPlaceholder(/customer name/i);
    await expect(customerNameInput).toBeVisible();
  });

  test('shows character counter for description field', async ({ page }) => {
    await expect(page.getByTestId('description-char-counter')).toBeVisible();
  });

  // --- Recent Projects List -----------------------------------------------

  test('shows empty state message when no projects exist', async ({ page }) => {
    await expect(
      page.getByText(/no projects yet/i),
    ).toBeVisible();
  });

  test('shows recent projects list when projects exist', async ({ page }) => {
    // Seed a project via API so the list has content
    await page.request.post('/api/projects', {
      data: { description: 'E2E seed project for landing page test' },
    });

    await page.reload();

    const projectCards = page.getByTestId('recent-project-card');
    await expect(projectCards.first()).toBeVisible();
  });

  test('each recent project shows description, status badge, and relative time', async ({
    page,
  }) => {
    await page.request.post('/api/projects', {
      data: { description: 'Recent project detail test' },
    });

    await page.reload();

    const card = page.getByTestId('recent-project-card').first();
    await expect(card.getByTestId('project-description')).toBeVisible();
    await expect(card.getByTestId('project-status-badge')).toBeVisible();
    await expect(card.getByText(/ago/i)).toBeVisible();
  });

  // --- Navigation ---------------------------------------------------------

  test('creating a project navigates to the chat page', async ({ page }) => {
    const descriptionInput = page.getByPlaceholder(
      /describe your customer.*scenario/i,
    );
    await descriptionInput.fill(
      'Build a real-time IoT dashboard on Azure for Contoso',
    );

    await page.getByRole('button', { name: /create project/i }).click();

    // Should redirect to /project/:uuid
    await expect(page).toHaveURL(/\/project\/[\w-]+/);
  });

  test('clicking a recent project navigates to its chat page', async ({
    page,
  }) => {
    // Seed a project
    const res = await page.request.post('/api/projects', {
      data: { description: 'Clickable project card test' },
    });
    const { projectId } = await res.json();

    await page.reload();

    await page.getByTestId('recent-project-card').first().click();

    await expect(page).toHaveURL(new RegExp(`/project/${projectId}`));
  });

  // --- Error state --------------------------------------------------------

  test('shows error banner when project creation fails', async ({ page }) => {
    const descriptionInput = page.getByPlaceholder(
      /describe your customer.*scenario/i,
    );
    // Fill with whitespace-only to bypass the disabled check but trigger server validation
    await descriptionInput.fill('   ');
    await page.getByRole('button', { name: /create project/i }).click();

    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('button', { name: /try again/i })).toBeVisible();
  });
});
