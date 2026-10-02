# User Roles

## Purpose
Document built-in HEFAISTOS roles and operational role assignment flow.

## Audience
Administrators managing access control and review workflows.

## Prerequisites
Admin-level access and an initialized user base.

## Steps / Workflow
1. Review role model (ADMIN, REVIEWER, ANALYST, VIEWER, ELONE, BOT roles).
2. Assign role values via administration workflows.
3. Validate role-specific access boundaries in UI and API behavior.

## Validation / Expected result
Users can only access actions and data permitted for their assigned role.

## Troubleshooting
If authorization appears inconsistent, confirm stored user role and organization context.

## Related pages
- [Authentication](authentication.md)
- [Waiting Room](../features/waiting-room.md)
- [GraphQL Reference](../api/graphql-reference.md)
