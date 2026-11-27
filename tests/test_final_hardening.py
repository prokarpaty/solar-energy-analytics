import os
import sys
import tempfile
import unittest

from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts")
)

from report_paths import secure_report_directory
from test_scheduler_reliability import s


class FinalHardeningTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_private_directory(self):
        path = self.root / "reports" / "daily"
        self.assertEqual(secure_report_directory(path), path)
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            secure_report_directory("reports/daily")

    def test_parent_traversal_rejected(self):
        with self.assertRaises(ValueError):
            secure_report_directory(self.root / ".." / "reports")

    def test_symlink_rejected(self):
        target = self.root / "target"
        target.mkdir(mode=0o700)
        link = self.root / "link"
        link.symlink_to(target)

        with self.assertRaises(ValueError):
            secure_report_directory(link / "daily")

    def test_insecure_permissions_rejected(self):
        path = self.root / "public"
        path.mkdir()
        path.chmod(0o755)

        with self.assertRaises(ValueError):
            secure_report_directory(path)

    def test_regular_file_rejected(self):
        path = self.root / "file"
        path.write_text("test")

        with self.assertRaises(ValueError):
            secure_report_directory(path)

    def make_job(self):
        scheduled = datetime(2026, 11, 25, tzinfo=s.TZ)
        report_id, source = s.report_details("daily", scheduled)

        return {
            "report_id": report_id,
            "report_type": "daily",
            "source": str(source),
            "scheduled_at": scheduled.isoformat()
        }, scheduled

    def test_valid_job_identity(self):
        with patch.object(s, "REPORTS", self.root):
            job, scheduled = self.make_job()
            s.validate_job_identity(job, scheduled)

    def test_wrong_job_path(self):
        with patch.object(s, "REPORTS", self.root):
            job, scheduled = self.make_job()
            job["source"] = "/tmp/incorrect.json"

            with self.assertRaises(ValueError):
                s.validate_job_identity(job, scheduled)

    def test_wrong_report_id(self):
        with patch.object(s, "REPORTS", self.root):
            job, scheduled = self.make_job()
            job["report_id"] = "incorrect"

            with self.assertRaises(ValueError):
                s.validate_job_identity(job, scheduled)

    def test_naive_timestamp(self):
        job, scheduled = self.make_job()

        with self.assertRaises(ValueError):
            s.validate_job_identity(
                job, scheduled.replace(tzinfo=None)
            )

    def test_future_timestamp(self):
        job, scheduled = self.make_job()

        with self.assertRaises(ValueError):
            s.validate_job_identity(
                job, s.now() + timedelta(days=1)
            )

    def test_wrong_dataset_period(self):
        job, scheduled = self.make_job()
        start, end = s.get_period("daily", now=scheduled)

        data = {
            "report_type": "daily",
            "timezone": s.REPORT_TZ.key,
            "start": (start - timedelta(days=1)).isoformat(),
            "end": end.isoformat()
        }

        with patch.object(
            s, "load_validated_report", return_value=data
        ):
            with self.assertRaises(ValueError):
                s.statistics_ready(
                    Path(job["source"]),
                    expected=("daily", scheduled)
                )


if __name__ == "__main__":
    unittest.main()
