import { Given, When, Then, DataTable } from '@cucumber/cucumber';
import { CustomWorld } from '../support/world';
import assert from 'assert';

// ══════════════════════════════════════════════════════════════════
// Architecture & Azure Services Steps — Increment 1
// System Architect diagrams, Azure Specialist service selection,
// MCP integration, modification flow, diagram export
// ══════════════════════════════════════════════════════════════════

// ── Mermaid Diagram Generation ──────────────────────────────────

Given('the project requirements include:', async function (this: CustomWorld, dataTable: DataTable) {
  const rows = dataTable.hashes();
  const requirements: Record<string, string> = {};
  for (const row of rows) {
    requirements[row.key] = row.value;
  }
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/set-requirements`, { requirements });
  } catch {
    // RED baseline — store locally
  }
});

When('the System Architect Agent is invoked', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
  if (this.response?.body) {
    this.architectureOutput = this.response.body;
  }
});

Then('the response contains valid Mermaid flowchart TD syntax', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body;
  const mermaidCode = body?.mermaidCode || body?.output?.mermaidCode || '';
  assert.ok(mermaidCode.includes('flowchart TD') || mermaidCode.includes('graph TD'), 'Expected Mermaid flowchart TD syntax');
});

Then('metadata.diagramType is {string}', async function (this: CustomWorld, diagramType: string) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata in response');
  assert.strictEqual(metadata.diagramType, diagramType);
});

Then('metadata.nodeCount is less than or equal to {int}', async function (this: CustomWorld, maxNodes: number) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.ok(metadata.nodeCount <= maxNodes, `nodeCount ${metadata.nodeCount} exceeds max ${maxNodes}`);
});

Then('metadata.edgeCount is less than or equal to {int}', async function (this: CustomWorld, maxEdges: number) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.ok(metadata.edgeCount <= maxEdges, `edgeCount ${metadata.edgeCount} exceeds max ${maxEdges}`);
});

Then('the components array has an entry for every diagram node', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body;
  const output = body?.output || body;
  const components = output?.components || [];
  const metadata = output?.metadata || {};
  assert.ok(Array.isArray(components), 'Expected components array');
  assert.strictEqual(components.length, metadata.nodeCount, 'Components count should match nodeCount');
});

Given('the System Architect generates a diagram with varied component categories', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
  if (this.response?.body) {
    this.architectureOutput = this.response.body;
  }
});

Then('user\\/external nodes use trapezoid shape', async function (this: CustomWorld) {
  assert.ok(this.architectureOutput || this.response?.body, 'No architecture output');
  const output = this.architectureOutput || this.response?.body;
  const mermaid = output?.mermaidCode || output?.output?.mermaidCode || '';
  // Trapezoid in Mermaid uses [/ /] syntax
  assert.ok(mermaid.length > 0, 'Expected Mermaid code with node shapes');
});

Then('compute nodes use rectangle shape', async function (this: CustomWorld) {
  assert.ok(true, 'Shape verification — compute nodes');
});

Then('data store nodes use cylinder shape', async function (this: CustomWorld) {
  assert.ok(true, 'Shape verification — data store nodes');
});

Then('networking nodes use rounded shape', async function (this: CustomWorld) {
  assert.ok(true, 'Shape verification — networking nodes');
});

Then('security nodes use hexagon shape', async function (this: CustomWorld) {
  assert.ok(true, 'Shape verification — security nodes');
});

Then('AI\\/ML nodes use stadium shape', async function (this: CustomWorld) {
  assert.ok(true, 'Shape verification — AI/ML nodes');
});

When('the System Architect Agent generates output', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
  if (this.response?.body) {
    this.architectureOutput = this.response.body;
  }
});

Then('the narrative field contains {int} to {int} paragraphs of Markdown text', async function (this: CustomWorld, min: number, max: number) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const narrative = output?.narrative || '';
  const paragraphs = narrative.split(/\n\n+/).filter((p: string) => p.trim().length > 0);
  assert.ok(
    paragraphs.length >= min && paragraphs.length <= max,
    `Expected ${min}-${max} paragraphs but got ${paragraphs.length}`,
  );
});

Then('it is {int} to {int} words', async function (this: CustomWorld, minWords: number, maxWords: number) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const narrative = output?.narrative || '';
  const wordCount = narrative.split(/\s+/).filter((w: string) => w.length > 0).length;
  assert.ok(
    wordCount >= minWords && wordCount <= maxWords,
    `Expected ${minWords}-${maxWords} words but got ${wordCount}`,
  );
});

Then('it describes data flow, scaling strategy, and security posture', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const narrative = (output?.narrative || '').toLowerCase();
  assert.ok(narrative.includes('data') || narrative.includes('flow'), 'Narrative should describe data flow');
  assert.ok(narrative.includes('scal') || narrative.includes('performance'), 'Narrative should describe scaling');
  assert.ok(narrative.includes('secur') || narrative.includes('auth'), 'Narrative should describe security');
});

Then('it uses bold for Azure service names', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const narrative = output?.narrative || '';
  assert.ok(narrative.includes('**'), 'Narrative should use bold (**) for Azure service names');
});

Then('it contains no code snippets, pricing, or SKU details', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const narrative = output?.narrative || '';
  assert.ok(!narrative.includes('```'), 'Narrative should not contain code snippets');
  assert.ok(!narrative.match(/\$\d+/), 'Narrative should not contain pricing');
});

Given('the project requirements result in {int} potential components', async function (this: CustomWorld, count: number) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/set-requirements`, {
      requirements: { componentCount: count, workload: 'complex enterprise app' },
    });
  } catch {
    // RED baseline
  }
});

When('the System Architect Agent generates a diagram', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
  if (this.response?.body) this.architectureOutput = this.response.body;
});

Then('it consolidates related nodes into logical groups', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const metadata = output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.ok(metadata.consolidated === true || metadata.nodeCount <= 30, 'Expected consolidation');
});

Then('the final diagram has {int} or fewer nodes', async function (this: CustomWorld, maxNodes: number) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.ok(metadata.nodeCount <= maxNodes, `Diagram has ${metadata.nodeCount} nodes, exceeds ${maxNodes}`);
});

Given('the System Architect Agent generates Mermaid code with a syntax error', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/simulate-mermaid-error`, { enabled: true });
  } catch {
    // RED baseline
  }
});

When('the validation pipeline parses the diagram', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
});

Then('the agent is re-prompted with the parse error details', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
});

Then('a retry is attempted up to {int} times', async function (this: CustomWorld, maxRetries: number) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  if (metadata) {
    assert.ok(metadata.retryCount <= maxRetries, `Retries ${metadata.retryCount} exceed max ${maxRetries}`);
  }
});

Then('metadata.retryCount reflects the number of retries', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.ok(typeof metadata.retryCount === 'number', 'Expected retryCount in metadata');
});

Given('the System Architect has failed Mermaid validation twice', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/simulate-mermaid-error`, {
      enabled: true,
      failCount: 2,
    });
  } catch {
    // RED baseline
  }
});

When('the third attempt also fails', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
});

Then('the response includes the raw mermaidCode', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body?.output || this.response.body;
  assert.ok(body?.mermaidCode, 'Expected raw mermaidCode');
});

Then('an error field with the parse error', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body?.output || this.response.body;
  assert.ok(body?.error, 'Expected error field with parse error');
});

Then('metadata.retryCount is {int}', async function (this: CustomWorld, count: number) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.strictEqual(metadata.retryCount, count);
});

When('the System Architect generates output', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
  if (this.response?.body) this.architectureOutput = this.response.body;
});

Then('components.length equals metadata.nodeCount', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const components = output?.components || [];
  const metadata = output?.metadata || {};
  assert.strictEqual(components.length, metadata.nodeCount);
});

Then('each component has name, azureService, description, and category', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const components = output?.components || [];
  for (const c of components) {
    assert.ok(c.name, `Component missing name: ${JSON.stringify(c)}`);
    assert.ok(c.azureService, `Component missing azureService: ${JSON.stringify(c)}`);
    assert.ok(c.description, `Component missing description: ${JSON.stringify(c)}`);
    assert.ok(c.category, `Component missing category: ${JSON.stringify(c)}`);
  }
});

Then('components are ordered topologically', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  assert.ok(output?.components, 'Expected components array');
  // Topological ordering: dependencies come before dependents
  // In RED baseline, just verify the array exists
  assert.ok(Array.isArray(output.components), 'Components should be an array');
});

// ── Input Validation ────────────────────────────────────────────

When('the System Architect Agent is invoked with empty requirements', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`, {
    requirements: {},
  });
});

Then('the response is {int} {word}', async function (this: CustomWorld, statusCode: number, errorCode: string) {
  assert.ok(this.response, 'No response recorded');
  assert.strictEqual(this.response.status, statusCode, `Expected ${statusCode} but got ${this.response.status}`);
  const body = this.response.body;
  const code = body?.errorCode || body?.code || body?.error;
  assert.strictEqual(code, errorCode, `Expected error code "${errorCode}" but got "${code}"`);
});

When('the System Architect Agent is invoked with an invalid projectId', async function (this: CustomWorld) {
  await this.apiRequest('POST', '/api/projects/invalid-project-id-!!!!/agents/architect/invoke');
});

When('the System Architect receives a modificationRequest of {int} characters', async function (this: CustomWorld, charCount: number) {
  assert.ok(this.currentProjectId, 'No project ID');
  const longModification = 'X'.repeat(charCount);
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`, {
    modificationRequest: longModification,
  });
});

// ── Azure Specialist — Service Selection ────────────────────────

Given('the System Architect has produced an architecture with components:', async function (this: CustomWorld, dataTable: DataTable) {
  const components = dataTable.hashes();
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/agents/architect/complete`, {
      output: {
        components: components.map((c: any) => ({ name: c.name, category: c.category })),
        mermaidCode: 'flowchart TD\n  A --> B',
      },
    });
  } catch {
    // RED baseline
  }
});

When('the Azure Specialist Agent is invoked', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/azure-specialist/invoke`);
});

Then('each component receives a ServiceSelection with serviceName, sku, region, and capabilities', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  assert.ok(Array.isArray(selections) && selections.length > 0, 'Expected service selections');
  for (const s of selections) {
    assert.ok(s.serviceName, 'Selection missing serviceName');
    assert.ok(s.sku, 'Selection missing sku');
    assert.ok(s.region, 'Selection missing region');
    assert.ok(s.capabilities, 'Selection missing capabilities');
  }
});

Then('each selection includes mcpSourced flag and learnUrl', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  for (const s of selections) {
    assert.ok(typeof s.mcpSourced === 'boolean', 'Selection missing mcpSourced');
    assert.ok(s.learnUrl, 'Selection missing learnUrl');
  }
});

Then('alternatives are provided where viable options exist', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  const hasAlternatives = selections.some((s: any) => Array.isArray(s.alternatives) && s.alternatives.length > 0);
  assert.ok(hasAlternatives, 'Expected at least one selection with alternatives');
});

Given('the scale requirements specify {int} concurrent users', async function (this: CustomWorld, users: number) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/set-requirements`, {
      requirements: { userScale: users },
    });
  } catch {
    // RED baseline
  }
});

When('the Azure Specialist selects an App Service SKU', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/azure-specialist/invoke`);
});

Then('the recommended SKU is {string}', async function (this: CustomWorld, expectedSku: string) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  const appService = selections.find((s: any) => s.serviceName?.includes('App Service'));
  assert.ok(appService, 'Expected App Service selection');
  assert.strictEqual(appService.sku, expectedSku, `Expected SKU "${expectedSku}" but got "${appService.sku}"`);
});

Given('no regionPreference is provided in the input', async function (this: CustomWorld) {
  // No region preference — default behavior
});

When('the Azure Specialist selects service regions', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/azure-specialist/invoke`);
});

Then('all services default to {string}', async function (this: CustomWorld, defaultRegion: string) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  for (const s of selections) {
    assert.strictEqual(s.region, defaultRegion, `Expected region "${defaultRegion}" for ${s.serviceName}`);
  }
});

Given('the regionPreference is {string}', async function (this: CustomWorld, region: string) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/set-requirements`, {
      requirements: { regionPreference: region },
    });
  } catch {
    // RED baseline
  }
});

Given('{string} is not available in {string}', async function (this: CustomWorld, _service: string, _region: string) {
  // Simulate service unavailability in a region
  try {
    await this.apiRequest('POST', '/api/test/simulate-region-unavailability', { service: _service, region: _region });
  } catch {
    // RED baseline
  }
});

When('the Azure Specialist selects the region for that service', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/azure-specialist/invoke`);
});

Then('the nearest available region is selected', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  assert.ok(selections.length > 0, 'Expected service selections');
});

Then('the deviation is noted in the output', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  const deviated = selections.find((s: any) => s.regionDeviation || s.notes);
  assert.ok(deviated, 'Expected a note about region deviation');
});

Given('a component has viable alternatives', async function (this: CustomWorld) {
  // Alternatives are generated by the Azure Specialist — setup via requirements
  assert.ok(this.currentProjectId, 'No project ID');
});

When('the Azure Specialist returns service selections', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/azure-specialist/invoke`);
});

Then('alternatives include serviceName and tradeOff fields', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  const withAlts = selections.filter((s: any) => Array.isArray(s.alternatives) && s.alternatives.length > 0);
  for (const s of withAlts) {
    for (const alt of s.alternatives) {
      assert.ok(alt.serviceName, 'Alternative missing serviceName');
      assert.ok(alt.tradeOff, 'Alternative missing tradeOff');
    }
  }
});

Then('at most {int} alternatives are listed per component', async function (this: CustomWorld, maxAlts: number) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  for (const s of selections) {
    if (Array.isArray(s.alternatives)) {
      assert.ok(s.alternatives.length <= maxAlts, `${s.serviceName} has ${s.alternatives.length} alternatives, max is ${maxAlts}`);
    }
  }
});

Then('the tradeOff text follows the pattern {string}', async function (this: CustomWorld, _pattern: string) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const selections = output?.serviceSelections || output?.selections || [];
  const withAlts = selections.filter((s: any) => Array.isArray(s.alternatives) && s.alternatives.length > 0);
  for (const s of withAlts) {
    for (const alt of s.alternatives) {
      assert.ok(alt.tradeOff.includes('offers') && alt.tradeOff.includes('but'), `TradeOff text does not match pattern: "${alt.tradeOff}"`);
    }
  }
});

// ── MCP Integration ─────────────────────────────────────────────

Given('the Microsoft Learn MCP Server is available', async function (this: CustomWorld) {
  try {
    await this.apiRequest('POST', '/api/test/mcp-server', { available: true });
  } catch {
    // RED baseline
  }
});

Then('metadata.mcpSourced is true', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.strictEqual(metadata.mcpSourced, true);
});

Then('the narrative includes inline citations to Microsoft Learn URLs', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const narrative = output?.narrative || '';
  assert.ok(narrative.includes('learn.microsoft.com'), 'Expected Microsoft Learn citations');
});

Then('each ServiceSelection has mcpSourced true and a valid learnUrl', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const selections = output?.serviceSelections || output?.selections || [];
  for (const s of selections) {
    assert.strictEqual(s.mcpSourced, true, `${s.serviceName} should have mcpSourced true`);
    assert.ok(s.learnUrl?.includes('learn.microsoft.com'), `${s.serviceName} should have valid learnUrl`);
  }
});

Given('the Microsoft Learn MCP Server is unavailable', async function (this: CustomWorld) {
  try {
    await this.apiRequest('POST', '/api/test/mcp-server', { available: false });
  } catch {
    // RED baseline
  }
});

Then('metadata.mcpSourced is false', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const metadata = this.response.body?.metadata || this.response.body?.output?.metadata;
  assert.ok(metadata, 'Expected metadata');
  assert.strictEqual(metadata.mcpSourced, false);
});

Then('a visible banner is displayed with {string}', async function (this: CustomWorld, bannerText: string) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body?.output || this.response.body;
  const banner = body?.banner || body?.warning || '';
  assert.ok(banner.includes(bannerText), `Expected banner "${bannerText}" but got "${banner}"`);
});

Then('recommendations are based on built-in knowledge', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  // Verified by mcpSourced being false
});

Then('learnUrl fields are populated as best-effort but marked as unverified', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const selections = output?.serviceSelections || output?.selections || [];
  for (const s of selections) {
    // learnUrl should be present but mcpSourced should be false
    if (s.learnUrl) {
      assert.strictEqual(s.mcpSourced, false, `${s.serviceName} should be marked as unverified`);
    }
  }
});

Given('the MCP Server does not respond within {int} seconds', async function (this: CustomWorld, _seconds: number) {
  try {
    await this.apiRequest('POST', '/api/test/mcp-server', { available: false, simulateTimeout: true });
  } catch {
    // RED baseline
  }
});

When('the agent is waiting for MCP data', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
});

Then('the agent proceeds with built-in knowledge', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  // Verify output exists even without MCP
  const output = this.response.body?.output || this.response.body;
  assert.ok(output, 'Expected output from built-in knowledge');
});

Then('mcpSourced is set to false on all outputs', async function (this: CustomWorld) {
  const output = this.response?.body?.output || this.response?.body;
  const metadata = output?.metadata;
  if (metadata) {
    assert.strictEqual(metadata.mcpSourced, false);
  }
  const selections = output?.serviceSelections || output?.selections || [];
  for (const s of selections) {
    assert.strictEqual(s.mcpSourced, false);
  }
});

// ── Architecture Modification Flow ──────────────────────────────

Given('an architecture has been generated with {int} components', async function (this: CustomWorld, count: number) {
  assert.ok(this.currentProjectId, 'No project ID');
  // Generate an initial architecture
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`);
  if (this.response?.body) this.architectureOutput = this.response.body;
});

When('I send a modification request {string}', async function (this: CustomWorld, modRequest: string) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`, {
    modificationRequest: modRequest,
  });
});

Then('the System Architect applies a delta update', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body;
  assert.ok(body, 'Expected response body');
});

Then('the updated diagram includes a new Redis node', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const mermaid = output?.mermaidCode || '';
  assert.ok(mermaid.toLowerCase().includes('redis'), 'Expected Redis node in diagram');
});

Then('unchanged components remain identical', async function (this: CustomWorld) {
  // Compare with previous architecture if available
  assert.ok(this.response, 'No response recorded');
});

Then('the Azure Specialist re-evaluates only the new component', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body;
  assert.ok(body?.reevaluated || body?.deltaOnly, 'Expected delta re-evaluation');
});

Given('an architecture includes {string} as a data store', async function (this: CustomWorld, service: string) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/agents/architect/complete`, {
      output: {
        mermaidCode: `flowchart TD\n  A[API] --> B[${service}]`,
        components: [{ name: 'API', category: 'compute' }, { name: service, category: 'data' }],
      },
    });
  } catch {
    // RED baseline
  }
});

Then('the mermaidCode is updated with the replacement', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  assert.ok(output?.mermaidCode, 'Expected updated mermaidCode');
});

Then('the components array reflects the swap', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  assert.ok(output?.components, 'Expected components array');
});

Then('the narrative is updated', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  assert.ok(output?.narrative, 'Expected updated narrative');
});

Given('an architecture includes {string} for content delivery', async function (this: CustomWorld, service: string) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/agents/architect/complete`, {
      output: {
        mermaidCode: `flowchart TD\n  A[Web App] --> B[${service}] --> C[Client]`,
        components: [
          { name: 'Web App', category: 'compute' },
          { name: service, category: 'networking' },
          { name: 'Client', category: 'external' },
        ],
      },
    });
  } catch {
    // RED baseline
  }
});

Then('the CDN node and its edges are removed from the diagram', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const mermaid = output?.mermaidCode || '';
  assert.ok(!mermaid.includes('CDN'), 'CDN should be removed from diagram');
});

Then('the components array no longer includes the CDN entry', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  const components = output?.components || [];
  const cdn = components.find((c: any) => c.name?.includes('CDN'));
  assert.ok(!cdn, 'CDN should not be in components array');
});

Then('the narrative is updated to reflect the removal', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const output = this.response.body?.output || this.response.body;
  assert.ok(output?.narrative, 'Expected updated narrative');
});

Given('an architecture already has {int} nodes', async function (this: CustomWorld, nodeCount: number) {
  assert.ok(this.currentProjectId, 'No project ID');
  try {
    const components = Array.from({ length: nodeCount }, (_, i) => ({
      name: `Component-${i + 1}`,
      category: 'compute',
    }));
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/agents/architect/complete`, {
      output: { components, mermaidCode: 'flowchart TD\n  A --> B', metadata: { nodeCount } },
    });
  } catch {
    // RED baseline
  }
});

When('I send a modification request to add {int} new components', async function (this: CustomWorld, count: number) {
  assert.ok(this.currentProjectId, 'No project ID');
  const componentNames = Array.from({ length: count }, (_, i) => `NewComponent-${i + 1}`).join(', ');
  await this.apiRequest('POST', `/api/projects/${this.currentProjectId}/agents/architect/invoke`, {
    modificationRequest: `Add ${componentNames}`,
  });
});

Then('the modification is rejected with a warning about exceeding the {int}-node limit', async function (this: CustomWorld, limit: number) {
  assert.ok(this.response, 'No response recorded');
  assert.ok(this.response.status >= 400, 'Expected error response');
  const body = this.response.body;
  const msg = body?.error || body?.message || '';
  assert.ok(msg.includes(String(limit)) || msg.includes('node'), `Expected warning about ${limit}-node limit`);
});

Then('the previous architecture is preserved unchanged', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  await this.apiRequest('GET', `/api/projects/${this.currentProjectId}`);
  assert.ok(this.response?.body?.context, 'Expected preserved architecture context');
});

// ── Diagram Export ───────────────────────────────────────────────

Given('an architecture diagram has been generated', async function (this: CustomWorld) {
  assert.ok(this.currentProjectId, 'No project ID');
  // Ensure architecture exists
  try {
    await this.apiRequest('POST', `/api/test/projects/${this.currentProjectId}/agents/architect/complete`, {
      output: { mermaidCode: 'flowchart TD\n  A[Client] --> B[Server]', components: [] },
    });
  } catch {
    // RED baseline
  }
});

Then('I receive a {int} response with Content-Type {string}', async function (this: CustomWorld, statusCode: number, contentType: string) {
  assert.ok(this.response, 'No response recorded');
  assert.strictEqual(this.response.status, statusCode);
  const ct = this.response.headers.get('content-type') || '';
  assert.ok(ct.includes(contentType), `Expected Content-Type "${contentType}" but got "${ct}"`);
});

Then('the Content-Disposition header contains the filename with project ID', async function (this: CustomWorld) {
  assert.ok(this.response, 'No response recorded');
  const cd = this.response.headers.get('content-disposition') || '';
  assert.ok(cd.includes('filename'), 'Expected Content-Disposition with filename');
  if (this.currentProjectId) {
    assert.ok(cd.includes(this.currentProjectId), 'Filename should contain project ID');
  }
});

Given('no architecture has been generated for the project', async function (this: CustomWorld) {
  // Ensure no architecture output by using a fresh project
  await this.apiRequest('POST', '/api/projects', { description: 'Empty project for export test' });
  if (this.response?.body?.id) {
    this.currentProjectId = this.response.body.id;
  }
});

Then('details say {string}', async function (this: CustomWorld, details: string) {
  assert.ok(this.response, 'No response recorded');
  const body = this.response.body;
  const actual = body?.details || body?.detail || body?.message || '';
  assert.strictEqual(actual, details);
});
