import sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
from email import policy
from email.parser import BytesParser
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from send_report import build_email, preview_report

class EmailTests(unittest.TestCase):
    data={'start':'2026-11-24T00:00:00+02:00','end':'2026-11-25T00:00:00+02:00','report_type':'daily','timezone':'Europe/Kyiv','energy':{'production':{'total':1.5,'coverage':100,'status':'complete'}}}
    def test_languages(self):
        for lang, label in [('en','Generation'),('uk','Генерація')]:
            subject,plain,html=build_email(self.data,lang)
            self.assertIn(label,plain)
            self.assertIn(label,html)
            self.assertIn(f'lang="{lang}"',html)
    def test_preview(self):
        with tempfile.TemporaryDirectory() as tmp, patch('send_report.smtplib.SMTP') as smtp:
            source=Path(tmp)/'report.json'
            source.write_text(json.dumps(self.data))
            for ext in ('.pdf','.html'): source.with_suffix(ext).write_bytes(b'test')
            path=preview_report(source,'en')
            msg=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
            self.assertEqual(len(list(msg.iter_attachments())),2)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            smtp.assert_not_called()
