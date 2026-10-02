# Security and CORS

## Purpose
Define deployment security controls for CORS/CSRF, WebAuthn, and TLS configuration.

## Audience
Operators hardening external-facing HEFAISTOS deployments.

## Prerequisites
Configured public domain and certificate assets.

## Steps / Workflow
1. Set canonical external URL values (`FRONTEND_URL`, `PUBLIC_BASE_URL`).
2. Configure `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
3. Configure WebAuthn relying-party values when security keys are enabled.
4. Deploy TLS certificates in NGINX certificate paths.

## Validation / Expected result
Users can authenticate securely over HTTPS and browser-origin restrictions behave as expected.

## Troubleshooting
If browsers block requests, re-check origin formatting and trusted origin list values.

## Related pages
- [Environment Variables](environment-variables.md)
- [Authentication](authentication.md)
- [System Update](../operations/system-update.md)
