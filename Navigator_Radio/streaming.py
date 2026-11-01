# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Lazy loopback handoff from Python HTTPS to Windows' legacy media player.

Only the selected station is fetched. No audio is saved, and private stream
URLs never reach the player's status/error text or the local request path.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import re
import threading
import urllib.request


class StreamRelay:
    def __init__(self, events):
        self.events = events
        self.url = ''
        self.token = ''
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                token, url = relay.token, relay.url
                if not token or self.path != '/' + token:
                    self.send_error(404)
                    return
                try:
                    request = urllib.request.Request(url, headers={
                        'User-Agent': 'EDMC-ShipRadio', 'Icy-MetaData': '1'})
                    with urllib.request.urlopen(request, timeout=12) as upstream:
                        if token != relay.token:
                            return
                        self.send_response(200)
                        self.send_header('Content-Type', upstream.headers.get('Content-Type', 'audio/mpeg'))
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        try:
                            interval = max(0, int(upstream.headers.get('icy-metaint', 0)))
                        except (ValueError, TypeError):
                            interval = 0
                        remaining, last_title = interval, ''
                        while token == relay.token:
                            chunk = upstream.read(min(8192, remaining) if interval else 8192)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            if interval:
                                remaining -= len(chunk)
                                if remaining == 0:
                                    size = upstream.read(1)
                                    if not size:
                                        break
                                    length = size[0] * 16
                                    metadata = upstream.read(length) if length else b''
                                    if len(metadata) < length:
                                        break
                                    text = metadata.rstrip(b'\0').decode('utf-8', errors='replace')
                                    match = re.search(r"(?:^|;)\s*StreamTitle='(.*?)';", text, re.S)
                                    if match and match[1] != last_title and token == relay.token:
                                        last_title = match[1]
                                        relay.events.put({'ev': 'metadata', 'title': last_title, 'stream_token': token})
                                    remaining = interval
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass  # player stopped or changed station
                except Exception:
                    if token == relay.token:
                        relay.events.put({'ev': 'error', 'what': 'media',
                                          'msg': 'Could not read the selected internet stream.'})
                    try:
                        self.send_error(502)
                    except OSError:
                        pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name='ShipRadioStream', daemon=True).start()

    def select(self, url):
        self.url = url
        self.token = secrets.token_urlsafe(24)
        return f'http://127.0.0.1:{self.server.server_port}/{self.token}'

    def stop(self):
        self.token = ''
        self.url = ''

    def close(self):
        self.stop()
        def shutdown():
            self.server.shutdown()
            self.server.server_close()
        threading.Thread(target=shutdown, name='ShipRadioStreamClose', daemon=True).start()
