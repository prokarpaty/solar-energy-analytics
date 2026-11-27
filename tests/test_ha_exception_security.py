import sys
import json
import unittest
import traceback

from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

import ha_client as ha


MARKER = "SYNTHETIC_HA_SECRET_LEAK_MARKER"


class HAExceptionSecurity(unittest.TestCase):

    def setUp(self):
        self.client = ha.HAClient.__new__(ha.HAClient)
        self.client.url = "http://127.0.0.1:8123"
        self.client.token = MARKER
        self.client.ws = None
        self.client.request_id = 0

    def assert_sanitized(self, operation):
        with self.assertRaises(RuntimeError) as ctx:
            operation()

        exc = ctx.exception

        self.assertNotIn(MARKER, str(exc))

        formatted = "".join(
            traceback.format_exception(exc)
        )

        self.assertNotIn(MARKER, formatted)

    def test_connection_failure(self):
        with patch.object(
            ha,
            "connect_websocket",
            side_effect=RuntimeError(MARKER)
        ):
            self.assert_sanitized(
                self.client.__enter__
            )

    def test_authentication_rejected(self):
        ws = MagicMock()

        ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({
                "type": "auth_invalid",
                "message": MARKER
            })
        ]

        with patch.object(
            ha, "connect_websocket", return_value=ws
        ):
            self.assert_sanitized(
                self.client.__enter__
            )

        ws.close.assert_called_once()
        self.assertIsNone(self.client.ws)

    def test_authentication_transport_failure(self):
        ws = MagicMock()

        ws.recv.return_value = json.dumps({
            "type": "auth_required"
        })

        ws.send.side_effect = RuntimeError(MARKER)

        with patch.object(
            ha, "connect_websocket", return_value=ws
        ):
            self.assert_sanitized(
                self.client.__enter__
            )

        ws.close.assert_called_once()

    def test_server_error(self):
        ws = MagicMock()

        ws.recv.return_value = json.dumps({
            "id": 1,
            "success": False,
            "error": {
                "code": "unknown_error",
                "message": MARKER
            }
        })

        self.client.ws = ws

        self.assert_sanitized(
            lambda: self.client.request("test")
        )

    def test_malformed_response(self):
        ws = MagicMock()
        ws.recv.return_value = MARKER

        self.client.ws = ws

        self.assert_sanitized(
            lambda: self.client.request("test")
        )

    def test_request_transport_failure(self):
        ws = MagicMock()
        ws.send.side_effect = RuntimeError(MARKER)

        self.client.ws = ws

        self.assert_sanitized(
            lambda: self.client.request("test")
        )

    def test_cleanup_failure(self):
        ws = MagicMock()
        ws.close.side_effect = RuntimeError(MARKER)

        self.client.ws = ws

        self.client.__exit__(None, None, None)

        self.assertIsNone(self.client.ws)

    def test_successful_authentication(self):
        ws = MagicMock()

        ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"})
        ]

        with patch.object(
            ha, "connect_websocket", return_value=ws
        ):
            with self.client:
                self.assertIs(self.client.ws, ws)

        ws.close.assert_called_once()

    def test_successful_request(self):
        ws = MagicMock()

        ws.recv.return_value = json.dumps({
            "id": 1,
            "success": True,
            "result": {"value": 123}
        })

        self.client.ws = ws

        self.assertEqual(
            self.client.request("test"),
            {"value": 123}
        )


if __name__ == "__main__":
    unittest.main()
