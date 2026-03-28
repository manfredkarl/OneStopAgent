# FRD-07: Codebase Cleanup — Remove v1 Architecture

## 1. Overview

The OneStopAgent codebase has been refactored from a TypeScript/Express/Next.js stack to Python/FastAPI + React/Vite. The old v1 code is still in the repo — unused, untested, and confusing. This FRD specifies exactly what to delete, what to keep, and what to update.

**Goal:** After this cleanup, the repo contains ONLY the v2 architecture. No dead code, no misleading config files, no abandoned specs.

---

## 2. Pre-Cleanup Safety

Before any deletion:

```bash
git branch backup/pre-v2-cleanup
git push origin backup/pre-v2-cleanup
```

This preserves the full history on a backup branch. All deletions happen on `main`.

---

## 3. DELETE: Old TypeScript Backend

**Directory:** `src/api/` (entire directory)

**Why:** Replaced by `src/python-api/`. Express.js routes, TypeScript services, Vitest tests, middleware — all superseded.

**Contains (~200 files):**
- `src/api/src/` — Express app, routes, services, models, middleware
- `src/api/tests/` — Vitest unit tests
- `src/api/package.json`, `tsconfig.json`, `Dockerfile`
- `src/api/node_modules/` (if present)

---

## 4. DELETE: Old Next.js Frontend

**Directory:** `src/web/` (entire directory)

**Why:** Replaced by `src/frontend/`. Next.js App Router pages, components, hooks — all superseded by Vite + React SPA.

**Contains (~150 files):**
- `src/web/src/app/` — pages, components, hooks, types
- `src/web/public/` — static assets
- `src/web/package.json`, `tsconfig.json`, `Dockerfile`, `next.config.ts`
- `src/web/.next/`, `src/web/node_modules/` (if present)

---

## 5. DELETE: Old Test Framework

### 5.1 `tests/` (entire directory)

**Why:** Cucumber/Gherkin step definitions for v1 Express backend. v2 uses Python pytest.

**Contains:**
- `tests/features/step-definitions/` — TypeScript step files (inc1-chat-steps.ts, inc1-architecture-steps.ts, etc.)
- `tests/features/support/` — world.ts, hooks.ts
- `tests/services/` — Vitest service tests

### 5.2 `e2e/` (entire directory)

**Why:** Playwright specs targeting old Next.js pages (landing.spec.ts, chat.spec.ts, auth.spec.ts, projects.spec.ts). v2 frontend has different routes, components, and data-testid attributes.

---

## 6. DELETE: Old v1 Specification Files

### 6.1 Root spec files (in `specs/`)

| File | Why Delete |
|------|-----------|
| `specs/prd.md` | v1 PRD (UserAuth → OneStopAgent). Superseded by `specs/v2/refactor.md` |
| `specs/frd-chat.md` | v1 FRD for Express chat API |
| `specs/frd-orchestration.md` | v1 FRD for old pipeline orchestration |
| `specs/frd-envisioning.md` | v1 FRD, replaced by BrainstormingAgent in v2 |
| `specs/frd-architecture.md` | v1 FRD, replaced by `specs/v2/frds/frd-03-solution-design.md` |
| `specs/frd-cost.md` | v1 FRD, replaced by `specs/v2/frds/frd-04-financial.md` |
| `specs/frd-business-value.md` | v1 FRD, replaced by `specs/v2/frds/frd-05-output.md` |
| `specs/frd-presentation.md` | v1 FRD, replaced by `specs/v2/frds/frd-05-output.md` |
| `specs/increments.md` | v1 increment planning, no longer applicable |
| `specs/openapi.yaml` | v1 Express API spec, Python API has different endpoints |

### 6.2 `specs/features/` (entire directory)

**Why:** v1 Gherkin scenarios (186 scenarios across 7 .feature files). Tied to old Express backend behavior. v2 has different agents, flow, and API contracts.

---

## 7. DELETE: Old Configuration Files (repo root)

| File | Why Delete |
|------|-----------|
| `tsconfig.json` (root) | Root TypeScript config for v1 tests/e2e. v2 backend is Python; frontend has its own tsconfig in `src/frontend/` |
| `cucumber.js` | Cucumber test runner config. v2 uses pytest, not Cucumber |
| `apphost.cs` | .NET Aspire host for old Express + Next.js. Not compatible with v2 stack |
| `aspire.config.json` | Aspire config pointing to `src/api` and `src/web` — both deleted |

---

## 8. DELETE: Old Documentation

| File | Why Delete |
|------|-----------|
| `docs/SHORTCOMINGS.md` | Analysis of v1 problems (pipeline invisible, callbacks broken). v2 solved these |
| `docs/PYTHON_REVIEW.md` | Review of early Python backend (ReAct agent issues). Superseded by v2 refactor |
| `docs/prototypes/` (entire directory) | HTML wireframes for v1 Next.js UI. v2 frontend is a different design |

---

## 9. DELETE: Unused Agent Files

| File | Why Delete |
|------|-----------|
| `src/python-api/agents/tools.py` | v1 `@tool` functions from LangChain ReAct approach. Logic migrated to individual agent classes |

---

## 10. DELETE: Old Root Scripts

| File | Why Delete |
|------|-----------|
| `scripts/generate-docs.ts` | TypeScript doc generator referencing v1 Gherkin features + Playwright screenshots |

---

## 11. UPDATE (Do Not Delete)

### 11.1 `package.json` (root)

Remove these obsolete scripts:
- `dev:api`, `dev:aspire`, `build:api`, `build:web`, `build:all`
- `test:api`, `test:cucumber`, `test:all`, `test:e2e`
- `docs:generate`, `docs:screenshots`, `docs:full`

Keep (if docs are still used):
- `docs:serve`, `docs:build`

Or: delete the root `package.json` entirely if v2 doesn't need root-level npm scripts (frontend and backend each have their own).

### 11.2 `package-lock.json` (root)

Delete if root `package.json` is deleted or stripped to minimal.

### 11.3 `azure.yaml`

Update service paths:
```yaml
services:
  api:
    project: ./src/python-api    # was ./src/api
    host: containerapp
    language: python              # was ts
  web:
    project: ./src/frontend       # was ./src/web
    host: containerapp
    language: ts
```

### 11.4 `.devcontainer/devcontainer.json`

Remove .NET Aspire SDK feature if not needed. Keep Python, Node, Azure CLI, Copilot.

### 11.5 `infra/` (Bicep files)

Audit for hardcoded references to `src/api` or `src/web`. Update paths to `src/python-api` and `src/frontend`.

### 11.6 `README.md`

Must be rewritten to reflect v2 architecture:
- Python backend (not Express)
- React frontend (not Next.js)
- Controlled orchestration (not spec2cloud pipeline)
- New startup instructions

### 11.7 `FUNCTIONAL_OVERVIEW.md`

Already partially updated. Verify it matches the current v2 architecture after cleanup.

### 11.8 `.github/workflows/`

Audit CI/CD workflows. Remove steps that build/test old TypeScript backend or Next.js frontend. Add steps for Python backend and Vite frontend if not present.

---

## 12. KEEP (No Changes)

| File/Directory | Why Keep |
|---------------|---------|
| `src/python-api/` | Active v2 backend |
| `src/frontend/` | Active v2 frontend |
| `specs/v2/` | Current v2 specs (refactor.md + 7 FRDs) |
| `docs/adrs/` | Architecture Decision Records — still valid |
| `docs/` root docs (architecture.md, concepts.md, greenfield.md, brownfield.md, skills.md) | spec2cloud framework docs — still relevant for context |
| `.github/skills/` | Agent skills for spec2cloud |
| `.github/copilot-instructions.md` | Copilot context |
| `infra/` | Azure deployment (after path updates) |
| `LICENSE`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CONTRIBUTING.md` | Governance docs |
| `.gitignore`, `.editorconfig` | General config |
| `.mcp.json` | MCP server configuration — needed for v2 KnowledgeAgent |
| `mkdocs.yml` | Docs site config (if still used) |

---

## 13. Execution Order

1. Create backup branch
2. Delete directories: `src/api/`, `src/web/`, `tests/`, `e2e/`, `specs/features/`, `docs/prototypes/`
3. Delete root files: `tsconfig.json`, `cucumber.js`, `apphost.cs`, `aspire.config.json`
4. Delete spec files: all `specs/*.md` and `specs/openapi.yaml` (NOT `specs/v2/`)
5. Delete docs: `docs/SHORTCOMINGS.md`, `docs/PYTHON_REVIEW.md`
6. Delete scripts: `scripts/generate-docs.ts`
7. Delete unused: `src/python-api/agents/tools.py`
8. Update: `azure.yaml`, root `package.json`, `.devcontainer/`, `README.md`
9. Audit: `infra/`, `.github/workflows/`
10. Commit: "chore: remove v1 architecture — Python FastAPI + React Vite only"

---

## 14. Acceptance Criteria

- [ ] `src/api/` does not exist
- [ ] `src/web/` does not exist
- [ ] `tests/` and `e2e/` do not exist
- [ ] No `.feature` files remain
- [ ] No v1 FRD files remain in `specs/` root
- [ ] `tsconfig.json`, `cucumber.js`, `apphost.cs`, `aspire.config.json` do not exist at root
- [ ] `src/python-api/agents/tools.py` does not exist
- [ ] `azure.yaml` points to `src/python-api` and `src/frontend`
- [ ] `README.md` describes v2 architecture (Python + React)
- [ ] Python backend starts: `uvicorn main:app --port 8000`
- [ ] React frontend starts: `npm run dev` in `src/frontend/`
- [ ] `git status` shows no untracked v1 artifacts
- [ ] Backup branch `backup/pre-v2-cleanup` exists with full history

---

## 15. Estimated Impact

| Metric | Before | After |
|--------|--------|-------|
| Total files | ~800+ | ~100 |
| Source directories | 4 (api, web, python-api, frontend) | 2 (python-api, frontend) |
| Config complexity | TypeScript + Python + .NET Aspire | Python + TypeScript (frontend only) |
| Test frameworks | Vitest + Cucumber + Playwright | pytest (future) |
| Spec documents | v1 (9 files) + v2 (8 files) | v2 only (8 files) |
