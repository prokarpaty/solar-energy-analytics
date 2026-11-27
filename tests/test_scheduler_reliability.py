import sys
import unittest
import tempfile
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
config = (Path(__file__).resolve().parents[1] / 'config/schedule.example.yaml').read_text()
with patch.object(Path, 'read_text', side_effect=lambda *a, **k: config), patch('secure_files.PrivateRotatingFileHandler'), patch('logging.basicConfig'), patch('signal.signal'):
    import scheduler as s

class SchedulerReliability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = sqlite3.connect(Path(self.tmp.name)/'jobs.db')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        self.clock = patch.object(s, 'now', return_value=datetime(2026,11,25,12,tzinfo=s.TZ))
        self.clock.start(); self.addCleanup(self.clock.stop)
        s.initialize(self.conn)
        self.conn.execute("UPDATE metadata SET value='2026-11-24T00:00:00+02:00'")
        self.conn.commit()
        s.enqueue_jobs(self.conn)
    def job(self):
        return self.conn.execute('SELECT * FROM jobs ORDER BY scheduled_at LIMIT 1').fetchone()
    def status(self, status, attempts=1):
        self.conn.execute('UPDATE jobs SET status=?, attempts=? WHERE report_id=?',(status,attempts,self.job()['report_id']))
        self.conn.commit()
    def test_enqueue_idempotent(self):
        count=self.conn.execute('SELECT count(*) FROM jobs').fetchone()[0]
        self.assertGreater(count,0)
        s.enqueue_jobs(self.conn)
        self.assertEqual(count,self.conn.execute('SELECT count(*) FROM jobs').fetchone()[0])
    def test_recover_generation(self):
        self.status('generating'); s.recover_interrupted_jobs(self.conn)
        self.assertEqual(self.job()['status'],'retry')
    def test_recover_exhausted(self):
        self.status('generating',s.MAX_ATTEMPTS); s.recover_interrupted_jobs(self.conn)
        self.assertEqual(self.job()['status'],'failed')
    def test_recover_sending(self):
        self.status('sending'); s.recover_interrupted_jobs(self.conn)
        self.assertEqual(self.job()['status'],'unknown')
    def test_no_repeat_sent(self):
        self.status('sent')
        with patch.dict(os.environ,{'SMTP_ENABLED':'true'}), patch.object(s,'run_script') as run:
            s.process_job(self.conn,self.job()); run.assert_not_called()
    def test_smtp_disabled(self):
        with patch.dict(os.environ,{'SMTP_ENABLED':'false'}), patch.object(s,'run_script') as run:
            s.process_job(self.conn,self.job()); run.assert_not_called()
        self.assertEqual(self.job()['attempts'],0)
    def test_generation_retry(self):
        with patch.dict(os.environ,{'SMTP_ENABLED':'true'}), patch.object(s,'run_script',side_effect=RuntimeError('test outage')), patch.object(s,'validate_job_identity'):
            s.process_job(self.conn,self.job())
        self.assertEqual(self.job()['status'],'retry'); self.assertEqual(self.job()['attempts'],1)
    def test_unknown_not_retried(self):
        self.status('unknown')
        with patch.dict(os.environ,{'SMTP_ENABLED':'true'}), patch.object(s,'run_script') as run:
            s.process_job(self.conn,self.job()); run.assert_not_called()
    def test_disabled_report(self):
        with patch.dict(s.CONFIG['reports']['daily'],{'enabled':False}), patch.dict(os.environ,{'SMTP_ENABLED':'true'}), patch.object(s,'run_script') as run:
            s.process_job(self.conn,self.job()); run.assert_not_called()
    def test_delivery_history_reconciliation(self):
        self.status('sending')
        folder=Path(self.tmp.name)
        (folder/'email-delivery.log').write_text(f"SUCCESS | {self.job()['report_id']}.json | Message-ID: <test>\n")
        with patch.object(s,'LOGS',folder):
            s.import_delivery_history(self.conn); s.recover_interrupted_jobs(self.conn)
        self.assertEqual(self.job()['status'],'sent')
    def test_final_hour_validation(self):
        import json
        end=datetime(2026,11,25,tzinfo=s.TZ)
        stamp=int(end.timestamp()*1000)-3600000
        row={'start':stamp,'end':stamp+3600000,'change':0}
        source=Path(self.tmp.name)/'report.json'
        for rows,expected in [([row],[]),([dict(row,change=True)],['production']),([dict(row,change=-1)],['production']),([row,dict(row,change=1)],['production'])]:
            source.write_text(json.dumps({'end':end.isoformat(),'energy':{'production':{}},'raw':{'energy':{'sensor.test':rows}}}))
            with patch.object(s,'SENSORS',{'energy':{'production':'sensor.test'}}), patch.object(s,'load_validated_report',return_value=json.loads(source.read_text())):
                self.assertEqual(s.statistics_ready(source),expected)
    def test_smtp_exit_classification(self):
        import subprocess
        for code, attempts, expected in [(20,0,'retry'),(20,s.MAX_ATTEMPTS-1,'failed'),(21,0,'failed'),(22,0,'unknown'),(1,0,'unknown'),(0,0,'sent')]:
            self.status('pending', attempts)
            source=Path(self.tmp.name)/'report.json'
            for ext in ('.pdf','.html'): source.with_suffix(ext).write_bytes(b'test')
            self.conn.execute('UPDATE jobs SET source=?, next_attempt=0 WHERE report_id=?',(str(source),self.job()['report_id']))
            self.conn.commit()
            def run(script,*args):
                if script=='send_report.py' and code: raise subprocess.CalledProcessError(code,script)
            with patch.dict(os.environ,{'SMTP_ENABLED':'true'}), patch.object(s,'run_script',side_effect=run), patch.object(s,'statistics_ready',return_value=[]), patch.object(s,'validate_job_identity'), patch.object(s,'import_delivery_history'):
                s.process_job(self.conn,self.job())
            self.assertEqual(self.job()['status'],expected)

    def test_generation_error_confidentiality(self):
        marker = "SYNTHETIC_SCHEDULER_SECRET_MARKER"

        with patch.dict(os.environ, {"SMTP_ENABLED": "true"}), \
             patch.object(s, "validate_job_identity"), \
             patch.object(s, "run_script",
                          side_effect=RuntimeError(marker)), \
             self.assertLogs(s.log, level="ERROR") as captured:

            s.process_job(self.conn, self.job())

        job = self.job()

        self.assertEqual(job["status"], "retry")
        self.assertEqual(job["attempts"], 1)
        self.assertEqual(
            job["last_error"],
            "Report generation failed"
        )
        self.assertNotIn(marker, job["last_error"])
        self.assertNotIn(marker, "\n".join(captured.output))

    def test_exhausted_error_confidentiality(self):
        marker = "SYNTHETIC_EXHAUSTED_SECRET_MARKER"

        self.status("pending", s.MAX_ATTEMPTS - 1)

        with patch.dict(os.environ, {"SMTP_ENABLED": "true"}), \
             patch.object(s, "validate_job_identity"), \
             patch.object(s, "run_script",
                          side_effect=RuntimeError(marker)), \
             self.assertLogs(s.log, level="ERROR") as captured:

            s.process_job(self.conn, self.job())

        job = self.job()

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["attempts"], s.MAX_ATTEMPTS)
        self.assertNotIn(marker, job["last_error"])
        self.assertNotIn(marker, "\n".join(captured.output))

    def test_subprocess_output_confidentiality(self):
        import subprocess

        marker = "SYNTHETIC_SUBPROCESS_SECRET_MARKER"

        with patch.object(s.subprocess, "run") as run, \
             self.assertLogs(s.log, level="INFO") as captured:

            s.run_script("generate_report.py", marker)

        kwargs = run.call_args.kwargs

        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 1800)
        self.assertNotIn(marker, "\n".join(captured.output))

    def test_subprocess_error_confidentiality(self):
        import subprocess

        marker = "SYNTHETIC_COMMAND_ERROR_MARKER"

        error = subprocess.CalledProcessError(
            1,
            ["generate_report.py", marker],
            output=marker,
            stderr=marker
        )

        with patch.dict(os.environ, {"SMTP_ENABLED": "true"}), \
             patch.object(s, "validate_job_identity"), \
             patch.object(s, "run_script", side_effect=error), \
             self.assertLogs(s.log, level="ERROR") as captured:

            s.process_job(self.conn, self.job())

        self.assertEqual(self.job()["status"], "retry")
        self.assertEqual(
            self.job()["last_error"],
            "Report subprocess failed"
        )
        self.assertNotIn(marker, "\n".join(captured.output))
