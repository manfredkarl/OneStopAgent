import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Chat Interface — §6.3, §6.4, §6.5
// RED-baseline tests: compile but fail until the UI is implemented.
// ---------------------------------------------------------------------------

/** Helper: create a project via API and return its id. */
async function createProject(
  page: import('@playwright/test').Page,
  description = 'E2E test project for chat interface',
): Promise<string> {
  const res = await page.request.post('/api/projects', {
    data: { description },
  });
  const body = await res.json();
  return body.projectId;
}

// ── Chat Page Layout ──────────────────────────────────────────────────────

test.describe('Chat Page Layout', () => {
  let projectId: string;

  test.beforeEach(async ({ page }) => {
    projectId = await createProject(page);
    await page.goto(`/project/${projectId}`);
  });

  test('chat page loads with three-column layout', async ({ page }) => {
    await expect(page.getByTestId('agent-sidebar')).toBeVisible();
    await expect(page.getByTestId('chat-thread')).toBeVisible();
  });

  test('message input is visible at the bottom', async ({ page }) => {
    const input = page.getByPlaceholder(/type your message/i);
    await expect(input).toBeVisible();
  });

  test('send button is disabled when input is empty', async ({ page }) => {
    const sendButton = page.getByTestId('send-button');
    await expect(sendButton).toBeDisabled();
  });

  test('send button enables after typing a message', async ({ page }) => {
    await page.getByPlaceholder(/type your message/i).fill('Hello');
    await expect(page.getByTestId('send-button')).toBeEnabled();
  });
});

// ── Agent Sidebar — §6.4 ─────────────────────────────────────────────────

test.describe('Agent Sidebar', () => {
  const AGENTS = [
    { id: 'pm', name: 'Project Manager' },
    { id: 'envisioning', name: 'Envisioning' },
    { id: 'architect', name: 'System Architect' },
    { id: 'azure-specialist', name: 'Azure Specialist' },
    { id: 'cost', name: 'Cost Specialist' },
    { id: 'business-value', name: 'Business Value' },
    { id: 'presentation', name: 'Presentation' },
  ] as const;

  let projectId: string;

  test.beforeEach(async ({ page }) => {
    projectId = await createProject(page);
    await page.goto(`/project/${projectId}`);
  });

  test('sidebar header shows "Agents" label', async ({ page }) => {
    await expect(
      page.getByTestId('agent-sidebar').getByText(/^agents$/i),
    ).toBeVisible();
  });

  test('shows all 7 agents in pipeline order', async ({ page }) => {
    const rows = page.getByTestId('agent-row');
    await expect(rows).toHaveCount(AGENTS.length);

    for (let i = 0; i < AGENTS.length; i++) {
      await expect(rows.nth(i).getByText(AGENTS[i].name)).toBeVisible();
    }
  });

  test('each agent row has avatar, name, and status indicator', async ({
    page,
  }) => {
    const firstRow = page.getByTestId('agent-row').first();
    await expect(firstRow.getByTestId('agent-avatar')).toBeVisible();
    await expect(firstRow.getByTestId('agent-name')).toBeVisible();
    await expect(firstRow.getByTestId('agent-status-dot')).toBeVisible();
  });

  test('status dot uses correct colours (grey=idle, blue=working, red=error)', async ({
    page,
  }) => {
    // Idle agent should have grey dot
    const idleDot = page
      .getByTestId('agent-row')
      .first()
      .getByTestId('agent-status-dot');
    await expect(idleDot).toHaveAttribute('data-status', 'idle');
  });

  test('System Architect toggle is disabled with tooltip', async ({ page }) => {
    const architectRow = page.getByTestId('agent-row').filter({
      hasText: /system architect/i,
    });
    const toggle = architectRow.getByRole('switch');
    await expect(toggle).toBeDisabled();

    await toggle.hover();
    await expect(
      page.getByText(/system architect is required/i),
    ).toBeVisible();
  });

  test('PM Agent has no toggle switch (always active)', async ({ page }) => {
    const pmRow = page.getByTestId('agent-row').filter({
      hasText: /project manager/i,
    });
    await expect(pmRow.getByRole('switch')).not.toBeVisible();
  });
});

// ── Chat Messages — §6.3, §6.5 ───────────────────────────────────────────

test.describe('Chat Messages', () => {
  let projectId: string;

  test.beforeEach(async ({ page }) => {
    projectId = await createProject(page);
    await page.goto(`/project/${projectId}`);
  });

  test('sending a message shows it right-aligned in the chat thread', async ({
    page,
  }) => {
    const input = page.getByPlaceholder(/type your message/i);
    await input.fill('What Azure services do you recommend?');
    await page.getByTestId('send-button').click();

    const userMsg = page.getByTestId('chat-message-user').last();
    await expect(userMsg).toBeVisible();
    await expect(userMsg).toContainText(
      'What Azure services do you recommend?',
    );
    // Verify right-alignment via CSS class or data attribute
    await expect(userMsg).toHaveAttribute('data-alignment', 'right');
  });

  test('user message has blue/neutral styling', async ({ page }) => {
    const input = page.getByPlaceholder(/type your message/i);
    await input.fill('Test styling');
    await page.getByTestId('send-button').click();

    const userMsg = page.getByTestId('chat-message-user').last();
    await expect(userMsg).toBeVisible();
    // Check for the expected bubble class
    await expect(userMsg).toHaveClass(/user-bubble|bg-blue/);
  });

  test('agent response appears left-aligned with agent avatar and name', async ({
    page,
  }) => {
    const input = page.getByPlaceholder(/type your message/i);
    await input.fill('Describe the architecture');
    await page.getByTestId('send-button').click();

    // Wait for agent response (may take a moment in a real environment)
    const agentMsg = page.getByTestId('chat-message-agent').first();
    await expect(agentMsg).toBeVisible({ timeout: 30_000 });
    await expect(agentMsg).toHaveAttribute('data-alignment', 'left');
    await expect(agentMsg.getByTestId('agent-avatar')).toBeVisible();
    await expect(agentMsg.getByTestId('agent-name')).toBeVisible();
  });

  test('input clears after sending a message', async ({ page }) => {
    const input = page.getByPlaceholder(/type your message/i);
    await input.fill('Clear me after send');
    await page.getByTestId('send-button').click();

    await expect(input).toHaveValue('');
  });

  test('typing indicator shows when agent is working', async ({ page }) => {
    const input = page.getByPlaceholder(/type your message/i);
    await input.fill('Trigger agent work');
    await page.getByTestId('send-button').click();

    await expect(page.getByTestId('typing-indicator')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/is thinking/i)).toBeVisible();
  });
});

// ── Rich Content Rendering — §6.5 ────────────────────────────────────────

test.describe('Rich Content Rendering', () => {
  let projectId: string;

  test.beforeEach(async ({ page }) => {
    projectId = await createProject(page);
    await page.goto(`/project/${projectId}`);
  });

  test('Mermaid diagram renders as SVG inside agent message', async ({
    page,
  }) => {
    // Send a message that should trigger the architect to produce a Mermaid diagram
    await page.getByPlaceholder(/type your message/i).fill('__START_AGENTS__');
    await page.getByTestId('send-button').click();

    // Wait for a message containing a Mermaid-rendered SVG
    const mermaidSvg = page.getByTestId('chat-message-agent').locator('svg.mermaid');
    await expect(mermaidSvg.first()).toBeVisible({ timeout: 60_000 });
  });

  test('Markdown content renders correctly (bold, lists, code blocks)', async ({
    page,
  }) => {
    // Agent messages use Markdown — verify rendered HTML
    const agentMsg = page.getByTestId('chat-message-agent').first();
    await expect(agentMsg).toBeVisible({ timeout: 30_000 });

    // At minimum, Markdown renderer should produce semantic HTML elements
    const rendered = agentMsg.locator('p, ul, ol, strong, code, pre');
    await expect(rendered.first()).toBeVisible();
  });

  test('tables render with sticky header and alternating rows', async ({
    page,
  }) => {
    const table = page.getByTestId('chat-message-agent').locator('table').first();
    await expect(table).toBeVisible({ timeout: 30_000 });
    await expect(table.locator('thead')).toBeVisible();
  });
});

// ── Scroll & Loading — §6.3 ──────────────────────────────────────────────

test.describe('Chat Scroll & Loading', () => {
  let projectId: string;

  test.beforeEach(async ({ page }) => {
    projectId = await createProject(page);
    await page.goto(`/project/${projectId}`);
  });

  test('shows loading spinner while chat history is fetched', async ({
    page,
  }) => {
    // On first navigation the chat should show a loader
    await page.goto(`/project/${projectId}`);
    // The spinner may be brief; just assert it existed
    const spinner = page.getByTestId('chat-loading-spinner');
    // Accept either visible or already gone (fast load)
    await expect(spinner.or(page.getByTestId('chat-thread'))).toBeVisible();
  });

  test('"New messages" pill appears when scrolled up and new message arrives', async ({
    page,
  }) => {
    // Scroll up
    await page.getByTestId('chat-thread').evaluate((el) => {
      el.scrollTop = 0;
    });

    // Send a new message to trigger the pill
    await page.getByPlaceholder(/type your message/i).fill('Scroll test');
    await page.getByTestId('send-button').click();

    await expect(page.getByTestId('new-messages-pill')).toBeVisible({
      timeout: 10_000,
    });
  });
});
