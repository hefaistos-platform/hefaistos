#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import time
from typing import Optional

JWT_RE = re.compile(r"^[A-Za-z0-9_\-=]+\.[A-Za-z0-9_\-=]+\.[A-Za-z0-9_\-=]+$")

def run(args, check=True, capture=False) -> subprocess.CompletedProcess:
    if capture:
        return subprocess.run(args, check=check, capture_output=True, text=True)
    return subprocess.run(args, check=check)

def extract_jwt_from_output(text: str) -> Optional[str]:
    # Search from the bottom up for a line that looks like a JWT
    for line in reversed(text.splitlines()):
        line = line.strip()
        if JWT_RE.match(line):
            return line
    return None

def load_secrets_from_files():
    """Read Docker secrets from /run/secrets/* and export as env vars"""
    secret_mappings = {
        'db_password': 'DB_PASSWORD',
        'rabbitmq_pass': 'RABBITMQ_PASS',
        'field_key': 'FIELD_ENCRYPTION_KEY',
        'mailgun_api': 'MAILGUN_API_KEY',
    }
    
    for secret_file, env_var in secret_mappings.items():
        secret_path = f'/run/secrets/{secret_file}'
        if os.path.isfile(secret_path):
            try:
                with open(secret_path, 'r') as f:
                    value = f.read().strip()
                    os.environ[env_var] = value
                    print(f"Loaded {env_var} from {secret_path}")
            except Exception as e:
                print(f"Warning: Could not read {secret_path}: {e}")

def run_migrations_with_retry(max_attempts: int = 10, initial_wait: float = 2.0) -> None:
    """Run Django migrations with retry and exponential backoff (handles DB not ready yet)."""
    wait = initial_wait
    for attempt in range(1, max_attempts + 1):
        print(f"Running Django migrations (attempt {attempt}/{max_attempts})...")
        result = subprocess.run([sys.executable, "manage.py", "migrate"], check=False)
        if result.returncode == 0:
            print("Migrations completed successfully.")
            return
        if attempt < max_attempts:
            print(f"Migrations failed (exit code {result.returncode}). "
                  f"Retrying in {wait:.0f}s...")
            time.sleep(wait)
            wait = min(wait * 2, 30)  # exponential backoff, capped at 30s
    raise RuntimeError(f"Migrations failed after {max_attempts} attempts.")


def check_no_model_drift() -> None:
    """Warn if there are unapplied model changes missing migration files."""
    result = run(
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        print("WARNING: Django model/migration drift detected.")
        print("Run `python manage.py makemigrations` and commit generated migration files.")

def collect_static_assets() -> None:
    """Collect Django static files for nginx (admin UI, GraphiQL assets, etc.)."""
    print("Collecting Django static files...")
    run([sys.executable, "manage.py", "collectstatic", "--noinput"], check=True)

def ensure_connector_token(token_file: str) -> None:
    try:
        proc = run([sys.executable, "manage.py", "generate_connector_token", "--no-color"], check=False, capture=True)
        token = extract_jwt_from_output(proc.stdout or "")
        if token:
            os.makedirs(os.path.dirname(token_file), exist_ok=True)
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(token)
            print(f"Wrote connector token to {token_file}")
        else:
            print("generate_connector_token did not produce a JWT; continuing without writing file")
    except Exception as e:
        print(f"Warning: could not generate connector token: {e}")


def start_lsp_servers():
    """Start SyntaxTide LSP servers for detection rule editing (optional, fails gracefully)."""
    if os.getenv("ENABLE_LSP_SERVERS", "").lower() not in ("1", "true", "yes"):
        print("LSP servers disabled (set ENABLE_LSP_SERVERS=true to enable).")
        return

    try:
        # Django must be configured before importing app modules
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
        django.setup()

        from lsp_server.manager import get_lsp_manager
        print("Starting SyntaxTide LSP servers...")
        manager = get_lsp_manager()
        manager.start_all()

        status = manager.get_status()
        for lang, info in status.items():
            if info['running']:
                print(f"LSP {lang.upper()} server running on port {info['port']} (PID: {info['pid']})")
            else:
                print(f"LSP {lang.upper()} server failed to start. Check logs for details.")
    except Exception as e:
        print(f"Warning: Failed to start LSP servers: {e}")
        print("LSP features will be unavailable. Detection editor will use GraphQL autocomplete only.")


def main():
    # 0) Load secrets from Docker secret files
    print("Loading secrets from Docker...")
    load_secrets_from_files()
    
    # 1) Run migrations with retry (DB may not be ready immediately)
    run_migrations_with_retry()

    # 2) Collect static files for nginx-served admin and GraphiQL assets.
    collect_static_assets()

    # 3) Warn (non-fatal) when model changes are missing committed migrations
    check_no_model_drift()

    # 4) Optionally generate and export token to shared file
    token_file = os.getenv("CONNECTOR_TOKEN_FILE")
    if token_file:
        print("Ensuring connector_svc JWT token is generated...")
        ensure_connector_token(token_file)

    # 5) Start LSP servers (optional, will gracefully fail if SyntaxTide unavailable)
    start_lsp_servers()

    # 6) Start dev server
    print("Starting Django development server...")
    os.execvp(sys.executable, [sys.executable, "manage.py", "runserver", "0.0.0.0:8000"])


if __name__ == "__main__":
    main()
