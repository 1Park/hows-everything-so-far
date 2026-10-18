"""Remove only dead-supervisor state before systemd starts the board app."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.config import load_settings  # noqa: E402
from scripts.dev import is_our_supervisor, port_free  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', default='.env.board')
    args = parser.parse_args()
    settings = load_settings(args.env_file)
    if not port_free(settings.controller_host, settings.controller_port) or not port_free(
        settings.stt_host, settings.stt_port
    ):
        raise RuntimeError('Controller or STT port is already in use; refusing to clear state')
    lock = ROOT / 'tmp' / f'dev-{settings.controller_port}.lock'
    if lock.exists():
        owner = lock.read_text().strip()
        if is_our_supervisor(int(owner)):
            raise RuntimeError(f'Supervisor {owner} is still running; refusing to clear state')
        # Do not remove a lock replaced by another starter while we checked its PID.
        if lock.read_text().strip() != owner:
            raise RuntimeError('Supervisor lock changed during startup')
        lock.unlink()
        print(f'Removed stale supervisor lock for PID {owner}', flush=True)
    lock.with_suffix('.stop').unlink(missing_ok=True)
    lock.with_suffix('.ready').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
