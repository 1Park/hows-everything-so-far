# Validation

The current tests and code are the source of truth. This document does not track fixed pass counts, running PIDs, or deployment state. Tests verify behavior with fixtures/fake backends and do not replace real model accuracy, NPU latency, or physical devices.

## Python

```sh
python -m pytest -q
python -m ruff check app common services scripts tests
```

Covers policy, schema, HTTP, cancel/confirm races, model worker lifetime, auto capture, and supervisor stop/restart. Router wire tests are skipped on platforms without Unix-domain sockets. Camera file tests need the optional OpenCV dependency.

## Browser

```sh
npm ci
npx playwright install chromium
python scripts/dev.py --mode offline
# in a separate terminal
npm run test:browser
npm run test:ui-regressions
REFILL_URL=http://127.0.0.1:8080 node scripts/browser_auto_capture.cjs
```

The board voice flow is tested with separate settings:

```sh
AUDIO_INPUT=fixture CAPTURE_MODE=auto CONTROLLER_PORT=8090   python scripts/dev.py --mode offline
REFILL_URL=http://127.0.0.1:8090 npm run test:board-voice
```

Environment variable examples are for a POSIX shell; in PowerShell, set them with `$env:NAME='value'`. `REFILL_URL` sets the app address, and `CHROME_PATH` sets an installed Chrome. Results are written to `tmp/browser-qa/`. The default browser tests use a virtual microphone.

## Real models and board

- `python scripts/smoke.py`: request, edit, Confirm, cancel, STT, and skip flows against a running Controller.
- `python scripts/evaluate_gemma.py --help`: evaluates 20 original / 20 synthetic distorted cases with the current product prompt. New results store the prompt input/output/time.
- `python scripts/benchmark_vision_residency.py --help`: compares CLI vs. resident latency and output equivalence with the same bundle and images.
- On site, separately check real images/voice, device disconnects, tablet listening, and the Bridge/MCU watchdog.

Past records are kept in [Gemma](gemma_evaluation/README.md), [Qwen](qwen_evaluation/README.md), [Vision](vision_evaluation/README.md), and [STT](stt_evaluation/README.md). Do not read results from earlier schemas, prompts, or bundles as the performance of the current code.
