import sys
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
import ssl
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ha_connection import validate_url, rest_open, connect_websocket, NoRedirect

class ConnectionTests(unittest.TestCase):
    def test_valid(self):
        for url in ('http://127.0.0.1:8123','http://192.168.50.134:8123','http://10.0.0.1','http://[::1]:8123','http://localhost','https://ha.example.com'):
            self.assertEqual(validate_url(url+'/'),url)
    def test_invalid(self):
        for url in ('http://8.8.8.8','http://ha.example.com','ftp://localhost','https://user:pass@host','https://host:0','https://host:99999','https://host:','https://host/path','https://host?','https://host#','https://host\\x','https://host\n','http://127.1','http://169.254.169.254'):
            with self.subTest(url=url), self.assertRaises(ValueError): validate_url(url)
    def test_redirect(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))
    def test_rest(self):
        with patch('urllib.request.build_opener') as build:
            rest_open('https://ha.example.com','/api/', 'test')
            self.assertEqual(build.call_args.args[0].proxies,{})
            self.assertEqual(build.call_args.args[2]._context.verify_mode,ssl.CERT_REQUIRED)
            self.assertTrue(build.call_args.args[2]._context.check_hostname)
    def test_ws(self):
        with patch('socket.create_connection') as tcp, \
             patch('ssl.create_default_context') as tls, \
             patch('websocket.create_connection') as connect:

            connect.return_value.getstatus.return_value = 101

            result = connect_websocket(
                'https://ha.example.com',
                timeout=10
            )

            tcp.assert_called_once_with(
                ('ha.example.com', 443),
                timeout=10
            )

            tls.return_value.wrap_socket.assert_called_once_with(
                tcp.return_value,
                server_hostname='ha.example.com'
            )

            connect.assert_called_once_with(
                'wss://ha.example.com/api/websocket',
                timeout=10,
                redirect_limit=0,
                socket=tls.return_value.wrap_socket.return_value
            )

            self.assertIs(result, connect.return_value)

    def test_ws_plain(self):
        with patch('socket.create_connection') as tcp, \
             patch('ssl.create_default_context') as tls, \
             patch('websocket.create_connection') as connect:

            connect.return_value.getstatus.return_value = 101

            connect_websocket('http://127.0.0.1:8123')

            tcp.assert_called_once_with(
                ('127.0.0.1', 8123),
                timeout=30
            )

            tls.assert_not_called()

            connect.assert_called_once_with(
                'ws://127.0.0.1:8123/api/websocket',
                timeout=30,
                redirect_limit=0,
                socket=tcp.return_value
            )

    def test_ws_redirect(self):
        with patch('socket.create_connection') as tcp, \
             patch('websocket.create_connection') as connect:

            connect.return_value.getstatus.return_value = 302

            with self.assertRaises(RuntimeError):
                connect_websocket('http://localhost')

            connect.return_value.shutdown.assert_called_once()
            tcp.return_value.close.assert_called_once()

    def test_ws_tls_failure(self):
        with patch('socket.create_connection') as tcp, \
             patch('ssl.create_default_context') as tls, \
             patch('websocket.create_connection') as connect:

            tls.return_value.wrap_socket.side_effect = (
                ssl.SSLCertVerificationError("test certificate")
            )

            with self.assertRaises(ssl.SSLCertVerificationError):
                connect_websocket('https://ha.example.com')

            tcp.return_value.close.assert_called_once()
            connect.assert_not_called()

    def test_ws_handshake_failure(self):
        with patch('socket.create_connection') as tcp, \
             patch('websocket.create_connection') as connect:

            connect.side_effect = RuntimeError("test handshake")

            with self.assertRaises(RuntimeError):
                connect_websocket('http://localhost')

            tcp.return_value.close.assert_called_once()

    def test_ws_secure_handshake_failure(self):
        with patch('socket.create_connection') as tcp, \
             patch('ssl.create_default_context') as tls, \
             patch('websocket.create_connection') as connect:

            connect.side_effect = RuntimeError("test handshake")

            with self.assertRaises(RuntimeError):
                connect_websocket('https://ha.example.com')

            tls.return_value.wrap_socket.return_value.close.assert_called_once()

    def test_ws_tcp_failure(self):
        with patch('socket.create_connection') as tcp, \
             patch('websocket.create_connection') as connect:

            tcp.side_effect = ConnectionRefusedError()

            with self.assertRaises(ConnectionRefusedError):
                connect_websocket('http://localhost')

            connect.assert_not_called()

    def test_ws_invalid_url(self):
        with patch('socket.create_connection') as tcp:
            with self.assertRaises(ValueError):
                connect_websocket('http://8.8.8.8')

            tcp.assert_not_called()
