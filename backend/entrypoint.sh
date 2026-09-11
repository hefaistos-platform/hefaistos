#!/bin/bash
set -e

# --- Read secrets from files if *_FILE env vars are set ---
if [ -n "${DB_PASSWORD_FILE:-}" ] && [ -f "$DB_PASSWORD_FILE" ]; then
	export DB_PASSWORD=$(cat "$DB_PASSWORD_FILE")
fi

if [ -n "${RABBITMQ_PASS_FILE:-}" ] && [ -f "$RABBITMQ_PASS_FILE" ]; then
	export RABBITMQ_PASS=$(cat "$RABBITMQ_PASS_FILE")
fi

if [ -n "${FIELD_ENCRYPTION_KEY_FILE:-}" ] && [ -f "$FIELD_ENCRYPTION_KEY_FILE" ]; then
	export FIELD_ENCRYPTION_KEY=$(cat "$FIELD_ENCRYPTION_KEY_FILE")
fi

if [ -n "${MAILGUN_API_KEY_FILE:-}" ] && [ -f "$MAILGUN_API_KEY_FILE" ]; then
	export MAILGUN_API_KEY=$(cat "$MAILGUN_API_KEY_FILE")
fi

echo "Running Django migrations..."
python manage.py migrate --no-input

echo "Ensuring connector_svc JWT token is generated..."
python manage.py generate_connector_token --no-color --quiet 2>/dev/null || true

if [ -n "${CONNECTOR_TOKEN_FILE:-}" ]; then
	echo "Writing connector token to $CONNECTOR_TOKEN_FILE (if available)..."
	# Extract the last non-empty line that looks like a JWT from the command output
	TOKEN_LINE=$(python manage.py generate_connector_token --no-color 2>/dev/null | tail -n 5 | grep -E '^[A-Za-z0-9_=\-]+\.[A-Za-z0-9_=\-]+\.[A-Za-z0-9_=\-]+$' | tail -n 1 || true)
	if [ -n "$TOKEN_LINE" ]; then
		echo -n "$TOKEN_LINE" > "$CONNECTOR_TOKEN_FILE"
	fi
fi

echo "Starting Django development server..."
exec python manage.py runserver 0.0.0.0:8000
