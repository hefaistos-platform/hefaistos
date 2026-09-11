# Billing Tab and Resource Manager (HEFAISTOS-Lemnian)

## Overview

This change adds organization-level billing and capacity management directly in HEFAISTOS:

- New **Billing** tab in **Configuration** (`/mgmt/config?tab=billing`)
- Stripe checkout flow for annual add-ons
- Capacity entitlements for:
  - extra users: **120 EUR/year each**
  - extra organizations: **10 EUR/year each**
- New role: **RESOURCE_MANAGER**
- Multi-organization management model (without replacing existing primary organization context)

## What Was Added

## 1) Backend data model

New models in `backend/organizations/models.py`:

- `OrganizationBillingProfile`
  - Stores Stripe linkage and capacity entitlements
  - Fields include:
    - `stripe_customer_id`
    - `stripe_subscription_id`
    - `included_users`, `extra_users`
    - `included_organizations`, `extra_organizations`
    - `last_checkout_session_id`, `last_payment_at`
  - Computed limits:
    - `max_users`
    - `max_organizations`

- `OrganizationManagerAccess`
  - Grants a user management access to additional organizations
  - Roles:
    - `OWNER`
    - `RESOURCE_MANAGER`

User limit enforcement follows `Organization.max_users` (`null` = unlimited).

## 2) New role

`RESOURCE_MANAGER` was added to `CustomUser.Roles` in `backend/identity/models.py`.

Behavior:

- Can access Configuration page
- Can invite users (subject to organization capacity)
- Can use Billing tab operations
- Can manage assigned organizations via `OrganizationManagerAccess`

## 3) Stripe integration

### GraphQL mutations (organizations schema)

Added in `backend/organizations/schema.py`:

- `createBillingAddonCheckoutSession(addExtraUsers, addExtraOrganizations, successUrl, cancelUrl)`
  - Creates Stripe checkout session for capacity add-ons
  - Returns checkout URL + session ID

- `createManagedOrganization(name)`
  - Creates additional organization if organization-capacity quota allows
  - Automatically links the creator as manager/owner access

- `assignOrganizationManager(userId, organizationId, accessRole)`
  - Grants cross-organization management access to users

### GraphQL queries (organizations schema)

- `myBillingProfile`
- `myManagedOrganizations`
- `myOrganizationManagerAccess`

### Webhook endpoint

Added in `backend/webhooks/stripe_billing_handler.py` and registered in `backend/webhooks/urls.py`:

- `POST /api/webhooks/stripe-billing/`

On `checkout.session.completed` with `billing_kind=capacity_addon` metadata:

- Increases `extra_users` / `extra_organizations` in `OrganizationBillingProfile`
- Syncs `Organization.max_users` to updated user capacity
- Stores last processed checkout session to prevent duplicate processing

## 4) Frontend Billing tab

Added in `frontend/src/pages/ConfigurationPage.tsx`:

- New `billing` tab key and UI
- Displays current quotas
- Allows selecting add-on quantities
- Starts Stripe checkout via GraphQL mutation
- Displays managed organizations list
- Allows creating managed organizations

Role UI updates:

- `RESOURCE_MANAGER` added to role selectors in:
  - `frontend/src/components/InviteUserModal.tsx`
  - `frontend/src/pages/ConfigurationPage.tsx` user edit/auth role section

## Environment Variables

Set these in deployment for Stripe billing:

- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_BILLING_SUCCESS_URL` (optional)
- `STRIPE_BILLING_CANCEL_URL` (optional)

Defaults for success/cancel URLs point back to `/mgmt/config?tab=billing` using `FRONTEND_URL`.

## Migrations

Added migrations:

- `backend/identity/migrations/0019_alter_customuser_role_add_resource_manager.py`
- `backend/organizations/migrations/0033_billing_profile_and_manager_access.py`

Run migrations after installing dependencies:

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
```

## Notes on multi-organization behavior

This implementation keeps existing `user.organization` as the **primary runtime context** for most platform modules.

Cross-organization administration is introduced via `OrganizationManagerAccess` and used for configuration/billing operations.

This avoids destabilizing existing organization-scoped workflows while enabling billing-driven org growth and delegated resource management.
