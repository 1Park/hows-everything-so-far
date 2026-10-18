from fastapi.testclient import TestClient

import app.server as server
from common.config import Settings


def test_ethernet_status_reads_kernel_link_and_counters(tmp_path):
    (tmp_path / 'statistics').mkdir()
    for name, value in {'carrier': '1', 'operstate': 'up', 'speed': '1000',
                        'carrier_changes': '4', 'statistics/rx_packets': '123',
                        'statistics/tx_packets': '456', 'statistics/rx_errors': '2'}.items():
        (tmp_path / name).write_text(value + '\n')
    status = server.ethernet_status(tmp_path)
    assert status['carrier'] == 1 and status['state'] == 'up'
    assert status['speed_mbps'] == 1000 and status['carrier_changes'] == 4
    assert status['rx_packets'] == 123 and status['tx_packets'] == 456
    assert status['rx_errors'] == 2 and status['tx_errors'] is None


def test_ethernet_status_handles_missing_or_unreadable_interface(tmp_path):
    status = server.ethernet_status(tmp_path / 'absent')
    assert status['carrier'] is None and status['state'] is None


def test_connection_status_is_uncached_and_independent_of_models(monkeypatch):
    monkeypatch.setattr(server, 'ethernet_status', lambda: {'carrier': 0, 'state': 'down'})
    settings = Settings(qwen_backend='fixture', tts_backend='disabled', audio_input='disabled')
    with TestClient(server.create_app(settings)) as client:
        response = client.get('/api/connection-status')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['ethernet'] == {'carrier': 0, 'state': 'down'}
        assert response.json()['client_ip'] == 'testclient'
        assert isinstance(response.json()['server_time'], float)
