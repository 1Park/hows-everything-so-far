"""Bounded on-board diagnostics, sampled even when the HTTP event loop stalls."""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty, Full, Queue


class ConnectionMonitor:
    def __init__(self, path, read_ethernet, clock=time.monotonic):
        self.path = Path(path)
        self.read_ethernet = read_ethernet
        self.clock = clock
        self.lock = threading.Lock()
        self.clients = {}
        self.last_tick = clock()
        self.last_link = None
        self.last_sample = None
        self.stale_clients = set()
        self.events = Queue(maxsize=128)
        self.stop_event = threading.Event()
        self.thread = None
        self.logger = logging.Logger('connection-monitor')
        self.handler = RotatingFileHandler(self.path, maxBytes=2_000_000, backupCount=3,
                                           encoding='utf-8', delay=True)
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(self.handler)

    def emit(self, event, **data):
        self.logger.info(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                                     'event': event, **data}, ensure_ascii=True))

    def event(self, event, **data):
        try:
            self.events.put_nowait((event, data))
        except Full:
            pass  # Diagnostics must never block the application.

    def tick(self):
        with self.lock:
            self.last_tick = self.clock()

    def seen(self, client_ip, status, latency_ms):
        with self.lock:
            if client_ip not in self.clients and len(self.clients) >= 32:
                oldest = min(self.clients, key=lambda ip: self.clients[ip]['seen'])
                self.clients.pop(oldest)
            self.clients[client_ip] = {'seen': self.clock(), 'http_status': status,
                                       'http_latency_ms': round(latency_ms)}

    def sample(self):
        now = self.clock()
        ethernet = self.read_ethernet()
        wifi = {}
        for name in ('carrier', 'operstate'):
            try:
                wifi[name] = Path(f'/sys/class/net/wlp3s0/{name}').read_text().strip()
            except OSError:
                wifi[name] = None
        with self.lock:
            clients = {ip: {'last_request_age_s': round(now - data['seen'], 1),
                            'stale': now - data['seen'] >= 10,
                            'http_status': data['http_status'],
                            'http_latency_ms': data['http_latency_ms']}
                       for ip, data in self.clients.items()}
            loop_age = round(now - self.last_tick, 1)
        snapshot = {'ethernet': ethernet, 'wifi': wifi, 'clients': clients,
                    'event_loop_age_s': loop_age}
        link = (ethernet.get('carrier'), ethernet.get('state'), ethernet.get('speed_mbps'),
                ethernet.get('carrier_changes'), wifi['carrier'], wifi['operstate'])
        if link != self.last_link:
            self.emit('link_change', **snapshot)
            self.last_link = link
        stale = {ip for ip, data in clients.items() if data['stale']}
        for ip in stale - self.stale_clients:
            self.emit('client_requests_stale', client_ip=ip, **snapshot)
        for ip in self.stale_clients - stale:
            if ip in clients:
                self.emit('client_requests_resumed', client_ip=ip, **snapshot)
        self.stale_clients = stale
        if self.last_sample is None or now - self.last_sample >= 5:
            self.emit('network_sample', **snapshot)
            self.last_sample = now
        while True:
            try:
                event, data = self.events.get_nowait()
            except Empty:
                break
            self.emit(event, **data)

    def run(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.emit('monitor_started', pid=os.getpid(), sample_interval_s=1,
                      periodic_log_interval_s=5, client_stale_after_s=10)
            while not self.stop_event.is_set():
                try:
                    self.sample()
                except Exception:
                    # Logging failures must not terminate sampling or HTTP services.
                    logging.getLogger(__name__).exception('Connection diagnostics sample failed')
                self.stop_event.wait(1)
            self.emit('monitor_stopped')
        finally:
            self.handler.close()

    def start(self):
        self.thread = threading.Thread(target=self.run, name='connection-monitor', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        else:
            self.handler.close()
