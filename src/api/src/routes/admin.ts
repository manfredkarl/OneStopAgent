import { type Express } from 'express';

export function mapAdminEndpoints(_app: Express): void {
  // Admin endpoints will be re-implemented with Entra ID RBAC in a later increment
  // Previously used UserAuth role checks; now superseded by project-scoped auth.
}
