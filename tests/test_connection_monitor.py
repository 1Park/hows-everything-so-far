import json

from app.connection_monitor import ConnectionMonitor


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_logs_link_loss_stale_tablet_and_recovery(tmp_path):
    now = [0.0]
    link = {'carrier': 1, 'state': 'up', 'carrier_changes': 2}
    path = tmp_path / 'connection.jsonl'
    monitor = ConnectionMonitor(path, lambda: link.copy(), clock=lambda: now[0])
    try:
        monitor.seen('192.168.50.2', 200, 8)
        monitor.sample()
        now[0] = 11
        link.update(carrier=0, state='down', carrier_changes=3)
        monitor.sample()
        outage = records(path)
        stale = next(row for row in outage if row['event'] == 'client_requests_stale')
        assert stale['ethernet']['carrier'] == 0
        assert stale['clients']['192.168.50.2']['last_request_age_s'] == 11
        assert stale['event_loop_age_s'] == 11  # Loop stalled; collector still writes.
        now[0] = 12
        monitor.tick()
        monitor.seen('192.168.50.2', 200, 17)
        link.update(carrier=1, state='up', carrier_changes=4)
        monitor.event('websocket_open', client_ip='192.168.50.2')
        monitor.sample()
        resumed = next(row for row in records(path) if row['event'] == 'client_requests_resumed')
        assert resumed['ethernet']['carrier'] == 1 and resumed['event_loop_age_s'] == 0
        assert resumed['clients']['192.168.50.2']['http_latency_ms'] == 17
        assert records(path)[-1]['event'] == 'websocket_open'
    finally:
        monitor.stop()


def test_rotates_logs_and_keeps_sampling_without_any_tablet(tmp_path):
    now = [0.0]
    path = tmp_path / 'connection.jsonl'
    monitor = ConnectionMonitor(path, lambda: {'carrier': 0}, clock=lambda: now[0])
    monitor.handler.maxBytes = 1600
    monitor.handler.backupCount = 2
    try:
        for i in range(30):
            now[0] = i * 5
            monitor.sample()
        files = list(tmp_path.glob('connection.jsonl*'))
        assert len(files) == 3
        assert all(file.stat().st_size <= 1600 for file in files)
        assert records(path)[-1]['event'] == 'network_sample'
        assert records(path)[-1]['clients'] == {}
    finally:
        monitor.stop()


def test_monitor_thread_starts_and_stops_without_http_requests(tmp_path):
    import threading

    sampled = threading.Event()

    def read_link():
        sampled.set()
        return {'carrier': 0}

    path = tmp_path / 'connection.jsonl'
    monitor = ConnectionMonitor(path, read_link)
    monitor.start()
    assert sampled.wait(2)
    monitor.stop()
    assert not monitor.thread.is_alive()
    assert records(path)[0]['event'] == 'monitor_started'
    assert records(path)[-1]['event'] == 'monitor_stopped'
