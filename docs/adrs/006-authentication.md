# ADR-006: Authentication Strategy

## Status
Accepted

## Date
2026-03-26

## Context
OneStopAgent is an internal Microsoft application used exclusively by @microsoft.com employees (Microsoft sellers). Authentication must integrate with the organisation's identity provider, support single sign-on (SSO), and produce JWT Bearer tokens for API authorisation. The backend must validate token signatures, issuers, audiences, and expiration (SEC-2). Every API endpoint must enforce ownership — projects are scoped to individual users via the `oid` (object ID) claim in the JWT (SEC-3, SEC-7). Rate limiting is keyed on the `oid` claim at 60 requests/minute/user (SEC-4). Transport security requires HTTPS with TLS 1.2+ and HSTS headers (SEC-8). The solution must operate within Microsoft tenant boundaries (NFR-8).

## Decision
Use **Microsoft Entra ID** (formerly Azure AD) with **MSAL.js** for frontend authentication and JWT Bearer token validation on the backend.

## Options Considered

### Option 1: Microsoft Entra ID with MSAL.js
**Pros:**
- Standard identity provider for all Microsoft internal applications — zero provisioning overhead
- MSAL.js handles the full token lifecycle: interactive login, silent token acquisition, token refresh, and cache management
- JWT tokens contain the `oid` claim used for ownership enforcement (SEC-3) and rate limiting (SEC-4)
- Supports conditional access policies, MFA, and compliance controls enforced by the organisation
- Native integration with Azure services (Cosmos DB RBAC, Azure AI Foundry, App Service authentication)
- Well-documented with official Microsoft libraries for React (MSAL React) and Node.js (MSAL Node)
- SSO experience — users are already signed into their Microsoft account

**Cons:**
- Tightly coupled to Microsoft identity infrastructure — not portable to non-Microsoft environments
- MSAL.js configuration requires correct tenant ID, client ID, and redirect URI setup
- Token validation logic must handle edge cases (clock skew, key rotation, multi-tenant vs. single-tenant)

### Option 2: Custom JWT Authentication
**Pros:**
- Full control over token format, claims, expiration, and signing
- No dependency on external identity providers
- Can be tailored to the exact claims needed by the application

**Cons:**
- Must build user registration, password management, and account recovery from scratch
- No SSO — users must create and manage separate credentials
- Must implement and maintain cryptographic signing, key rotation, and token revocation
- Does not leverage existing Microsoft identity infrastructure
- Compliance and security audit burden shifts entirely to the application team
- Violates Microsoft internal security standards for employee-facing applications

### Option 3: Azure AD B2C
**Pros:**
- Supports custom user journeys, social identity providers, and external users
- Flexible policy-based authentication flows
- Scalable for consumer-facing applications

**Cons:**
- Designed for external/consumer-facing applications, not internal employee apps
- Adds unnecessary complexity — custom policies, user flows, and identity experience framework
- Higher cost compared to standard Entra ID (which is included with Microsoft 365)
- @microsoft.com users already have Entra ID accounts — B2C adds a redundant identity layer
- Not aligned with Microsoft internal application standards

## Rationale
Microsoft Entra ID with MSAL.js is the unambiguous choice for an internal Microsoft application. Every @microsoft.com user already has an Entra ID account through their Microsoft 365 license — there is no user provisioning, no password management, and no account recovery to build. MSAL.js (specifically `@azure/msal-react` for the React frontend) provides a production-tested library for the complete authentication flow: redirect-based login, silent token acquisition, automatic token refresh, and in-memory token caching.

The JWT tokens issued by Entra ID contain the `oid` (object ID) claim that serves as the universal user identifier throughout the application. This claim is used for:
- **Ownership enforcement (SEC-3):** Every API endpoint extracts `oid` from the token and compares it to `project.userId`. Mismatches return `403 Forbidden`.
- **Rate limiting (SEC-4):** 60 requests/minute keyed on `oid`.
- **Data isolation (SEC-7):** All database queries include a `userId` filter derived from `oid`.
- **Audit logging (SEC-6):** Every API request logs `userId` (from `oid`), action, project ID, status code, timestamp, and IP address.

Backend token validation (SEC-2) verifies the JWT signature against Entra ID's published signing keys, checks the issuer (`https://login.microsoftonline.com/{tenantId}/v2.0`), validates the audience (application's client ID), and rejects expired tokens with `401 Unauthorized`.

Custom JWT authentication was rejected because it would require building identity infrastructure that already exists and would violate Microsoft internal security standards. Azure AD B2C is designed for external users and adds unnecessary complexity and cost for an internal-only application.

## Consequences
**Positive:**
- Zero user provisioning — all @microsoft.com employees can sign in immediately
- SSO experience — users are typically already authenticated via their browser session
- MSAL.js handles token lifecycle complexity (acquisition, refresh, cache, retry)
- `oid` claim provides a stable, unique user identifier for ownership, rate limiting, and audit
- Organisational conditional access policies (MFA, device compliance) are automatically enforced
- Well-supported by Microsoft with official SDKs, documentation, and security updates

**Negative:**
- Application is not portable to non-Microsoft identity providers without significant rework
- Requires correct Entra ID app registration configuration (client ID, tenant ID, redirect URIs, API permissions)
- Token validation must handle Entra ID-specific edge cases (key rotation via JWKS endpoint, v1 vs. v2 token formats)
- Local development requires either a real Entra ID app registration or a mock authentication layer

## References
- PRD §9 — Technical Stack: "Microsoft Entra ID (SSO with @microsoft.com)"
- PRD §4.8 FR-8 — Authentication & Authorisation
- PRD §5 NFR-8 — Data Residency & LLM Privacy (Microsoft tenant boundaries)
- frd-chat.md §5 SEC-1 — Authentication: "Microsoft Entra ID SSO, MSAL, Bearer JWT"
- frd-chat.md §5 SEC-2 — Token Validation: "JWT signature, issuer, audience, expiration"
- frd-chat.md §5 SEC-3 — Ownership Enforcement: "`oid` claim vs. `project.userId`, 403 on mismatch"
- frd-chat.md §5 SEC-4 — Rate Limiting: "60 req/min/user keyed on `oid`"
- frd-chat.md §5 SEC-6 — Audit Logging: "userId, action, projectId, statusCode, timestamp, ipAddress"
- frd-chat.md §5 SEC-7 — Data Isolation: "Projects scoped to individual users"
- frd-chat.md §5 SEC-8 — Transport Security: "HTTPS only, TLS 1.2+, HSTS"
