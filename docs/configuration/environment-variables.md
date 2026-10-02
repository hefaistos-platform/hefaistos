# Environment Variables

## Purpose
Summarize runtime configuration keys used by HEFAISTOS and where they apply.

## Audience
Operators configuring deployments and maintainers troubleshooting runtime behavior.

## Prerequisites
A generated `.env` file and secrets directory.

## Steps / Workflow
1. Configure core database, RabbitMQ, and encryption values.
2. Configure auth and JWT settings.
3. Configure CORS/CSRF/frontend URL values.
4. Configure optional integrations (email, AI providers, search, connectors).
5. Keep sensitive values in Docker secrets where supported.

## Validation / Expected result
Services load expected settings and start without configuration-related failures.

## Troubleshooting
If services fail to start, verify variable names against `Docs/ENVIRONMENT_VARIABLES.md` and check container logs for missing keys.

## Related pages
- [Authentication](authentication.md)
- [Security and CORS](security-and-cors.md)
- [Service Matrix](../operations/service-matrix.md)
