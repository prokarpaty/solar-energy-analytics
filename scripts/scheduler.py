import os
import re
import sys
from report_loader import load_validated_report
from report_paths import secure_report_directory
import time
import yaml
import signal
import sqlite3
import logging
import argparse
import subprocess
import fcntl

from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from schedule_times import delivery_ready_at
from secure_files import PrivateRotatingFileHandler, private_append, private_database

from ha_client import get_period, CONFIG as SENSORS, TZ as REPORT_TZ, numeric, valid_rows


BASE = Path("/app")
STATE = BASE / "state"
LOGS = BASE / "logs"
SCRIPTS = BASE / "scripts"

REPORTS = Path(
    os.environ.get("REPORT_DIRECTORY", "/app/reports")
)

DB = STATE / "scheduler.sqlite"

CONFIG = yaml.safe_load(
    (BASE / "config/schedule.yaml").read_text()
)

TZ = ZoneInfo(CONFIG["timezone"])
if TZ.key != REPORT_TZ.key:
    raise ValueError("Schedule timezone must match REPORT_TIMEZONE")
SETTINGS = CONFIG["scheduler"]

CHECK_INTERVAL = SETTINGS["check_interval_seconds"]
DELAY = SETTINGS["statistics_delay_minutes"]
RETRY = SETTINGS["retry_interval_minutes"]
MAX_ATTEMPTS = SETTINGS["max_attempts"]
CATCH_UP_DAYS = SETTINGS["catch_up_days"]

STOP = False

logging.Formatter.converter = time.gmtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s UTC | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        PrivateRotatingFileHandler(
            LOGS / "scheduler.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
    ]
)

log = logging.getLogger("solar-scheduler")


def now():
    return datetime.now(TZ)


def stop_handler(signum, frame):
    global STOP
    STOP = True
    log.info("Shutdown requested")


signal.signal(signal.SIGTERM, stop_handler)
signal.signal(signal.SIGINT, stop_handler)


def connect():
    conn = private_database(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def initialize(conn):

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            report_id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            last_error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status
        ON jobs(status, next_attempt);
    """)

    conn.execute("""
        INSERT OR IGNORE INTO metadata(key, value)
        VALUES ('activated_at', ?)
    """, (now().isoformat(),))

    conn.commit()


def report_details(report_type, scheduled):

    start, end = get_period(
        report_type,
        now=scheduled
    )

    last = end.date() - timedelta(days=1)

    report_id = (
        f"solar-{report_type}-"
        f"{start.date()}_{last}"
    )

    source = (
        REPORTS / report_type /
        f"{report_id}.json"
    )

    return report_id, source


def import_delivery_history(conn):

    path = LOGS / "email-delivery.log"

    if not path.exists():
        return

    pattern = re.compile(
        r"SUCCESS \| "
        r"(solar-(daily|weekly|monthly|quarterly|yearly)-"
        r"\d{4}-\d{2}-\d{2}_"
        r"(\d{4}-\d{2}-\d{2}))\.json"
        r" \| Message-ID:"
    )

    imported = 0

    for line in path.read_text(
        encoding="utf-8",
        errors="replace"
    ).splitlines():

        match = pattern.search(line)

        if not match:
            continue

        report_id, report_type, last = match.groups()

        scheduled = (
            datetime.fromisoformat(last)
            .replace(tzinfo=TZ)
            + timedelta(days=1)
        )

        source = (
            REPORTS / report_type /
            f"{report_id}.json"
        )

        cursor = conn.execute("""
            INSERT INTO jobs (
                report_id, report_type,
                scheduled_at, source,
                status, updated_at
            )
            VALUES (?, ?, ?, ?, 'sent', ?)
            ON CONFLICT(report_id) DO UPDATE SET
                status = 'sent',
                updated_at = excluded.updated_at,
                last_error = NULL
            WHERE jobs.status != 'sent'
        """, (
            report_id,
            report_type,
            scheduled.isoformat(),
            str(source),
            now().isoformat()
        ))

        imported += cursor.rowcount

    conn.commit()

    log.info(
        "Imported or reconciled %d successful deliveries",
        imported
    )


def recover_interrupted_jobs(conn):

    conn.execute("""
        UPDATE jobs
        SET status = CASE WHEN attempts >= ? THEN 'failed' ELSE 'retry' END,
            next_attempt = 0,
            updated_at = ?,
            last_error = 'Interrupted during generation'
        WHERE status = 'generating'
    """, (MAX_ATTEMPTS, now().isoformat()))

    conn.execute("""
        UPDATE jobs
        SET status = 'unknown',
            updated_at = ?,
            last_error = 'Interrupted during SMTP delivery'
        WHERE status = 'sending'
    """, (now().isoformat(),))

    conn.commit()


def is_scheduled(report_type, day):

    if report_type == "daily":
        return True

    if report_type == "weekly":
        return day.weekday() == 0

    if report_type == "monthly":
        return day.day == 1

    if report_type == "quarterly":
        return (
            day.day == 1
            and day.month in (1, 4, 7, 10)
        )

    if report_type == "yearly":
        return day.month == 1 and day.day == 1

    return False


def enqueue_jobs(conn):

    current = now()

    activated = datetime.fromisoformat(
        conn.execute("""
            SELECT value FROM metadata
            WHERE key = 'activated_at'
        """).fetchone()["value"]
    )

    days = (
        CATCH_UP_DAYS
        if SETTINGS.get("catch_up", True)
        else 0
    )

    for offset in range(days, -1, -1):

        scheduled = (
            current - timedelta(days=offset)
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        if scheduled > current:
            continue

        for report_type, config in CONFIG["reports"].items():

            if not config["enabled"]:
                continue

            if not is_scheduled(report_type, scheduled):
                continue

            report_id, source = report_details(
                report_type, scheduled
            )

            ready_at = delivery_ready_at(scheduled, config, DELAY)

            if ready_at < activated.timestamp():
                continue

            cursor = conn.execute("""
                INSERT OR IGNORE INTO jobs (
                    report_id, report_type,
                    scheduled_at, source,
                    status, next_attempt, updated_at
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
            """, (
                report_id,
                report_type,
                scheduled.isoformat(),
                str(source),
                ready_at,
                current.isoformat()
            ))

            if cursor.rowcount:
                log.info(
                    "Queued %s | ready at %s",
                    report_id,
                    datetime.fromtimestamp(
                        ready_at, TZ
                    ).isoformat()
                )

    conn.commit()


def update_job(conn, report_id, status,
               error=None, next_attempt=0):

    conn.execute("""
        UPDATE jobs
        SET status = ?,
            last_error = ?,
            next_attempt = ?,
            updated_at = ?
        WHERE report_id = ?
    """, (
        status,
        error,
        next_attempt,
        now().isoformat(),
        report_id
    ))

    conn.commit()


def run_script(script, *args):

    command = [
        sys.executable,
        str(SCRIPTS / script),
        *map(str, args)
    ]

    log.info("Executing %s", script)

    subprocess.run(
        command,
        check=True,
        timeout=1800,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def statistics_ready(source, *, expected=None):

    data = load_validated_report(
        source, energy_mapping=SENSORS["energy"]
    )

    if expected is not None:
        report_type, scheduled = expected
        start, end = get_period(report_type, now=scheduled)

        if (
            data["report_type"] != report_type
            or data["timezone"] != REPORT_TZ.key
            or datetime.fromisoformat(data["start"]) != start
            or datetime.fromisoformat(data["end"]) != end
        ):
            raise ValueError("Scheduled report identity mismatch")

    end = datetime.fromisoformat(data["end"])

    last_hour = int(
        (end.timestamp() - 3600) * 1000
    )

    raw = data["raw"]["energy"]

    missing = []

    for name, entity in SENSORS["energy"].items():
        if name not in data["energy"]:
            continue

        rows = raw.get(entity, [])

        valid = valid_rows(rows, datetime.fromtimestamp(last_hour / 1000, TZ), end)
        found = any(
            numeric(row.get("change"))
            and row["change"] >= 0
            for row in valid.values()
        )
        if not found:
            missing.append(name)

    return missing


def validate_job_identity(job, scheduled):
    if scheduled.tzinfo is None:
        raise ValueError("Invalid scheduled timestamp")

    local = scheduled.astimezone(TZ)

    if (
        local.hour or local.minute
        or local.second or local.microsecond
        or local > now()
        or not is_scheduled(job["report_type"], local)
    ):
        raise ValueError("Invalid scheduled report period")

    report_id, expected_source = report_details(
        job["report_type"], local
    )

    if (
        job["report_id"] != report_id
        or Path(job["source"]) != expected_source
    ):
        raise ValueError("Invalid scheduled report path")

    secure_report_directory(expected_source.parent)


def process_job(conn, job):

    report_id = job["report_id"]
    source = Path(job["source"])

    if STOP or not CONFIG["reports"].get(job["report_type"], {}).get("enabled"):
        return
    if os.getenv("SMTP_ENABLED", "").lower() != "true":
        return

    # Claim and increment in a single durable transaction.
    cursor = conn.execute("""
        UPDATE jobs SET attempts = attempts + 1, status = 'generating',
            updated_at = ?, last_error = NULL
        WHERE report_id = ? AND status IN ('pending', 'retry')
            AND attempts < ? AND next_attempt <= ?
    """, (now().isoformat(), report_id, MAX_ATTEMPTS, time.time()))
    conn.commit()
    if not cursor.rowcount:
        return
    attempts = conn.execute("SELECT attempts FROM jobs WHERE report_id = ?",
                            (report_id,)).fetchone()[0]

    log.info(
        "Processing %s | attempt %d/%d",
        report_id, attempts, MAX_ATTEMPTS
    )

    try:

        scheduled = datetime.fromisoformat(
            job["scheduled_at"]
        )

        validate_job_identity(job, scheduled)

        run_script(
            "generate_report.py",
            "--type", job["report_type"],
            "--as-of", scheduled.date()
        )

        missing = statistics_ready(
            source,
            expected=(job["report_type"], scheduled)
        )

        if missing and attempts < MAX_ATTEMPTS:

            raise RuntimeError(
                "Final-hour statistics missing: "
                + ", ".join(missing)
            )

        if missing:
            log.warning(
                "Sending report with incomplete data: %s",
                ", ".join(missing)
            )

        run_script(
            "render_report.py",
            source
        )

        for extension in (".pdf", ".html"):

            attachment = source.with_suffix(extension)

            if (
                not attachment.is_file()
                or attachment.stat().st_size == 0
            ):
                raise RuntimeError(
                    f"Invalid attachment: {attachment}"
                )

        if STOP:
            update_job(
                conn, report_id, "failed" if attempts >= MAX_ATTEMPTS else "retry",
                "Shutdown before sending"
            )
            return

    except Exception as exc:

        if isinstance(exc, subprocess.TimeoutExpired):
            error = "Report subprocess timed out"
        elif isinstance(exc, subprocess.CalledProcessError):
            error = "Report subprocess failed"
        elif isinstance(exc, OSError):
            error = "Report filesystem or process error"
        else:
            error = "Report generation failed"

        log.error(
            "%s: %s",
            error,
            report_id
        )

        if attempts < MAX_ATTEMPTS:

            update_job(
                conn,
                report_id,
                "retry",
                error,
                time.time() + RETRY * 60
            )

        else:

            update_job(
                conn,
                report_id,
                "failed",
                error
            )

        return

    import_delivery_history(conn)
    if conn.execute("SELECT status FROM jobs WHERE report_id = ?", (report_id,)).fetchone()[0] == "sent":
        return
    update_job(conn, report_id, "sending")

    try:

        run_script(
            "send_report.py",
            source
        )

    except Exception as exc:

        # Reconcile any SMTP success recorded before
        # the process terminated.
        import_delivery_history(conn)

        status = conn.execute("""
            SELECT status FROM jobs
            WHERE report_id = ?
        """, (report_id,)).fetchone()["status"]

        if status != "sent":
            code = exc.returncode if isinstance(exc, subprocess.CalledProcessError) else None
            outcome = {20: "retry", 21: "failed", 22: "unknown"}.get(code, "unknown")
            if outcome == "retry" and attempts >= MAX_ATTEMPTS:
                outcome = "failed"
            update_job(conn, report_id, outcome,
                       f"SMTP subprocess outcome: {code}",
                       time.time() + RETRY * 60 if outcome == "retry" else 0)
            log.warning("SMTP delivery %s: %s", outcome, report_id)

        return

    update_job(conn, report_id, "sent")

    log.info("DELIVERED | %s", report_id)


def show_status(conn):

    print("\n=== SCHEDULER DELIVERY HISTORY ===\n")

    for row in conn.execute("""
        SELECT report_id, status, attempts, updated_at
        FROM jobs
        ORDER BY scheduled_at DESC, report_type
    """):

        print(
            f"{row['report_id']:48} "
            f"{row['status']:12} "
            f"attempts={row['attempts']} "
            f"{row['updated_at']}"
        )


def show_schedule():

    print("\n=== NEXT SCHEDULED REPORTS ===\n")

    current = now()

    for report_type, config in CONFIG["reports"].items():

        if not config["enabled"]:

            print(f"{report_type:12} DISABLED")
            continue

        for offset in range(367):

            candidate = (
                current + timedelta(days=offset)
            ).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )

            if not is_scheduled(report_type, candidate):
                continue

            ready_at = datetime.fromtimestamp(
                delivery_ready_at(candidate, config, DELAY), TZ
            )
            if ready_at <= current:
                continue

            report_id, _ = report_details(
                report_type, candidate
            )
            print(
                f"{report_type:12} {ready_at.isoformat()} | "
                f"{report_id}"
            )

            break


def main():
    os.umask(0o077)

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--init", action="store_true"
    )

    parser.add_argument(
        "--status", action="store_true"
    )

    parser.add_argument(
        "--schedule", action="store_true"
    )

    args = parser.parse_args()

    if args.schedule:
        show_schedule()
        return

    if args.status:
        with connect() as conn:
            show_status(conn)
        return

    lock = private_append(STATE / "scheduler.lock")

    try:
        fcntl.flock(
            lock,
            fcntl.LOCK_EX | fcntl.LOCK_NB
        )
    except BlockingIOError:
        raise SystemExit("Scheduler already running")

    with connect() as conn:

        initialize(conn)

        import_delivery_history(conn)

        recover_interrupted_jobs(conn)

        if args.init:

            show_status(conn)
            show_schedule()
            return

        log.info(
            "Solar Reports scheduler started | timezone=%s",
            TZ
        )

        show_schedule()

        while not STOP:

            try:

                enqueue_jobs(conn)

                job = next((row for row in conn.execute("""
                    SELECT * FROM jobs
                    WHERE status IN ('pending', 'retry')
                      AND next_attempt <= ? AND attempts < ?
                    ORDER BY scheduled_at,
                        CASE report_type
                            WHEN 'daily' THEN 1
                            WHEN 'weekly' THEN 2
                            WHEN 'monthly' THEN 3
                            WHEN 'quarterly' THEN 4
                            WHEN 'yearly' THEN 5
                            ELSE 6
                        END
                """, (time.time(), MAX_ATTEMPTS))
                    if CONFIG["reports"].get(row["report_type"], {}).get("enabled")
                    and os.getenv("SMTP_ENABLED", "").lower() == "true"), None)

                if job:

                    process_job(conn, job)
                    continue

            except Exception:

                log.error("Scheduler loop failed")

            for _ in range(CHECK_INTERVAL):

                if STOP:
                    break

                time.sleep(1)

        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
