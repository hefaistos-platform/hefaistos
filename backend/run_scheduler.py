#!/usr/bin/env python
"""
Scheduler service that runs periodic tasks like scheduled repository pulls.

Can be run in two modes:
1. Loop mode (default): Runs continuously, checking every 5 minutes
2. Single mode (--once): Runs once and exits (for use with external schedulers like cron/Ofelia)

Usage:
    python run_scheduler.py          # Continuous loop mode
    python run_scheduler.py --once   # Single execution mode
"""
import os
import sys
import time
import logging
import argparse
import django

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


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
                with open(secret_path, 'r', encoding='utf-8') as f:
                    value = f.read().strip()
                    os.environ[env_var] = value
                    logger.debug("Loaded %s from %s", env_var, secret_path)
            except Exception as e:
                logger.warning("Could not read %s: %s", secret_path, e)


# Setup Django
load_secrets_from_files()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.management import call_command
from organizations.ai_tasks import run_due_ai_tasks

# Configuration
CHECK_INTERVAL_SECONDS = 300  # 5 minutes between checks


def run_scheduled_pulls():
    """Execute the scheduled pulls management command."""
    try:
        logger.info("Running scheduled repository pulls check...")
        call_command('run_scheduled_pulls')
        logger.info("Scheduled pulls check completed.")
        return True
    except Exception as e:
        logger.error(f"Error running scheduled pulls: {e}")
        return False


def run_scheduled_rag_syncs():
    """Execute the scheduled RAG template sync management command."""
    try:
        logger.info("Running scheduled repository RAG sync check...")
        call_command('run_scheduled_rag_syncs')
        logger.info("Scheduled repository RAG sync check completed.")
        return True
    except Exception as e:
        logger.error("Error running scheduled RAG syncs: %s", e)
        return False


def run_scheduled_hefaistos_pulls():
    """Execute the scheduled HEFAISTOS remote peer pulls command."""
    try:
        logger.info("Running scheduled HEFAISTOS remote pulls check...")
        call_command('run_scheduled_hefaistos_pulls')
        logger.info("Scheduled HEFAISTOS remote pulls check completed.")
        return True
    except Exception as e:
        logger.error("Error running scheduled HEFAISTOS remote pulls: %s", e)
        return False


def run_scheduled_misp_pulls():
    """Execute the scheduled MISP Waiting Room auto-pull management command."""
    try:
        logger.info("Running scheduled MISP Waiting Room auto-pull check...")
        call_command('run_scheduled_misp_pulls')
        logger.info("Scheduled MISP Waiting Room auto-pull check completed.")
        return True
    except Exception as e:
        logger.error("Error running scheduled MISP auto-pulls: %s", e)
        return False


def run_scheduled_ai_tasks():
    """Execute due organization AI-assisted scheduled tasks."""
    try:
        logger.info("Running scheduled organization AI tasks check...")
        result = run_due_ai_tasks()
        logger.info(
            "Organization AI tasks check completed (ran=%s, initialized=%s, failed=%s).",
            result.get('ran', 0),
            result.get('initialized', 0),
            result.get('failed', 0),
        )
        return True
    except Exception as e:
        logger.error("Error running scheduled organization AI tasks: %s", e)
        return False



def maybe_send_news_digest():
    """Send weekly news digest on configured schedule.
    Default: Monday at 08:00 UTC, runs once per day.
    """
    try:
        import datetime
        now = datetime.datetime.utcnow()
        # Configurable schedule via env vars
        day_name = os.environ.get('DIGEST_DAY', 'MONDAY').upper()
        hour = int(os.environ.get('DIGEST_HOUR', '8'))

        weekday_map = {
            'MONDAY': 0, 'TUESDAY': 1, 'WEDNESDAY': 2,
            'THURSDAY': 3, 'FRIDAY': 4, 'SATURDAY': 5, 'SUNDAY': 6
        }
        target_weekday = weekday_map.get(day_name, 0)

        # Only consider the 10-minute window starting at target hour
        in_window = (now.weekday() == target_weekday) and (now.hour == hour) and (0 <= now.minute < 10)
        if not in_window:
            return False

        # Check feature flag from NewsSettings
        try:
            from news.models import NewsSettings
            settings = NewsSettings.get_solo()
            if not settings.digest_enabled:
                logger.info("Digest sending disabled in NewsSettings; skipping.")
                return False
        except Exception as e:
            logger.warning(f"Could not read NewsSettings: {e}")

        marker_path = '/tmp/news_digest_last_sent'
        last_sent_date = None
        try:
            with open(marker_path, 'r') as f:
                last_sent_date = f.read().strip()
        except FileNotFoundError:
            pass

        today = now.date().isoformat()
        if last_sent_date == today:
            logger.info("News digest already sent today; skipping.")
            return False

        logger.info("Sending weekly news digest...")
        call_command('send_news_digest')
        with open(marker_path, 'w') as f:
            f.write(today)
        logger.info("Weekly news digest sent.")
        return True
    except Exception as e:
        logger.error(f"Error sending news digest: {e}")
        return False


def run_loop():
    """Run scheduler in continuous loop mode."""
    logger.info("=" * 60)
    logger.info("Hefaistos Scheduler Service Starting (Loop Mode)")
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS} seconds ({CHECK_INTERVAL_SECONDS // 60} minutes)")
    logger.info("=" * 60)
    
    # Initial delay to let other services start
    logger.info("Waiting 30 seconds for services to initialize...")
    time.sleep(30)
    
    while True:
        try:
            # Run scheduled pulls
            run_scheduled_pulls()

            # Run scheduled repository RAG syncs
            run_scheduled_rag_syncs()

            # Run scheduled instance-to-instance HEFAISTOS pulls
            run_scheduled_hefaistos_pulls()

            # Run scheduled MISP Waiting Room auto-pulls
            run_scheduled_misp_pulls()

            # Run scheduled organization AI tasks
            run_scheduled_ai_tasks()

            # Maybe send weekly news digest
            maybe_send_news_digest()
            
            # Add more scheduled tasks here in the future
            # e.g., cleanup_old_logs(), refresh_threat_intel(), etc.
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        
        # Wait before next check
        logger.info(f"Next check in {CHECK_INTERVAL_SECONDS // 60} minutes...")
        time.sleep(CHECK_INTERVAL_SECONDS)


def run_once():
    """Run scheduler once and exit (for use with Ofelia/cron)."""
    logger.info("Hefaistos Scheduler - Single Execution Mode")
    success = run_scheduled_pulls()
    success = run_scheduled_rag_syncs() and success
    success = run_scheduled_hefaistos_pulls() and success
    success = run_scheduled_misp_pulls() and success
    run_scheduled_ai_tasks()
    # Also attempt digest once (respects schedule window)
    maybe_send_news_digest()
    sys.exit(0 if success else 1)


def main():
    parser = argparse.ArgumentParser(description='Hefaistos Scheduler Service')
    parser.add_argument('--once', action='store_true', 
                        help='Run once and exit (for use with Ofelia/cron)')
    args = parser.parse_args()
    
    if args.once:
        run_once()
    else:
        run_loop()


if __name__ == '__main__':
    main()
