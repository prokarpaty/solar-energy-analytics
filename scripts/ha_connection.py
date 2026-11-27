"""Direct, validated Home Assistant connections."""
import ipaddress
import re
import ssl
import socket
import urllib.request
from urllib.parse import urlsplit


def validate_url(url):
    if not isinstance(url, str) or re.search(r'[^\x21-\x7e]|[\\%?#@]', url):
        raise ValueError('Unsafe Home Assistant URL')
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.path not in ('', '/') or p.username is not None or p.password is not None:
        raise ValueError('Expected HTTP(S) origin without credentials or path')
    port = p.port
    if port == 0 or p.netloc.endswith(':'):
        raise ValueError('Invalid port')
    host = p.hostname
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
        if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*', host):
            raise ValueError('Invalid hostname')
    if p.scheme == 'http':
        networks = ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '::1/128', 'fc00::/7')
        if host != 'localhost' and not (ip and any(ip in ipaddress.ip_network(n) for n in networks)):
            raise ValueError('HTTPS required for non-local Home Assistant')
    return url.rstrip('/')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def rest_open(url, endpoint, token=None, timeout=30):
    base = validate_url(url)
    if endpoint not in ('/api/', '/api/states'):
        raise ValueError('Unsupported HA endpoint')
    headers = {'Accept': 'application/json'}
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    return opener.open(urllib.request.Request(base + endpoint, headers=headers), timeout=timeout)



def connect_websocket(url, timeout=30):
    import websocket

    base = validate_url(url)
    parsed = urlsplit(base)

    secure = parsed.scheme == "https"
    host = parsed.hostname
    port = parsed.port or (443 if secure else 80)

    ws_url = (
        ("wss" if secure else "ws")
        + base[base.index(":"):]
        + "/api/websocket"
    )

    sock = socket.create_connection(
        (host, port),
        timeout=timeout
    )

    try:
        if secure:
            context = ssl.create_default_context()

            sock = context.wrap_socket(
                sock,
                server_hostname=host
            )

        ws = websocket.create_connection(
            ws_url,
            timeout=timeout,
            redirect_limit=0,
            socket=sock
        )

        if ws.getstatus() != 101:
            ws.shutdown()
            raise RuntimeError(
                "Unexpected WebSocket handshake status"
            )

        return ws

    except BaseException:
        sock.close()
        raise
