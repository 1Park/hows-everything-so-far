# Automatic/manual capture

Runs in: the Controller Python process (`app/capture.py`). It uses the existing single `VideoSource` and the Vision HTTP/fixture API. The resident DINO/YOLO workers, weights, detection/crop, and pre/post-processing are not changed.

## Usage

In the UI, select **Demo tools & diagnostics → Capture mode → Automatic**. The camera stays live and the progress time of the class-stability check is shown. Selecting it for the first time also enables the browser speaker. If the page is refreshed later, browser policy may require pressing Enable sound again.

1. By default, the latest raw image is sent to Vision every 0.5 s (2 per second). Multiple inferences are never requested at once; a slow call is waited for.
2. **The object count and the count per class** must stay the same for 3 s. Example: water 1 / coffee 2 / unknown 1. object_id, detection order, box coordinates, and fill level are not part of the class-stability criterion. Object tracking/position-lock checks are not implemented.
3. The stability window restarts when there are no objects, when the count/class/source changes, or when a call/camera error occurs. An observation gap longer than 3× the normal interval (at least 1 s) also resets the window.
4. Within the 3 s window, the image with the smallest **union area of regions where two or more bboxes overlap** is chosen. The area is normalized to the original image, and a region covered by three boxes is not counted twice. On a tie, the latest image is chosen.
5. The chosen image and its exact VisionResult are frozen together. With no additional Vision call, the existing Controller flow continues: policy → prompt → board recording → STT → LLM → request accepted. Whether Confirm is used follows the `REQUIRE_CONFIRMATION` setting. Scenes with only enough drink left / low confidence / unknown are skipped as in the existing policy.

**Manual** captures immediately with the existing Start demo / Inspect again buttons. In automatic mode, **Restart auto capture** in the Start position starts a new stability window and does not freeze immediately. To start from an uploaded image while in automatic mode, switch to Manual. Periodic scanning always uses the camera/server video input and the normal scenario.

## Restart and cancel

- Scanning stops while serving a customer, during LLM processing, while a card is shown, and during a mock sequence. Changing the mode mid-flow does not cancel or newly approve the existing request/card.
- The default after completion, decline, cancel, skip, or error is **wait 10 s → automatic restart → new 3 s stability check**. While waiting, only video is shown live and Vision checks pause; the same class/count composition is checked again after the restart. The timer does not run on the first start or while serving a customer.
- The remaining time is shown next to Restart auto capture. The automatic-restart checkbox in Demo tools turns it off, or changes the wait to 1–300 s. Changing the time while waiting restarts the count from that moment. A manual restart clears the wait immediately, and switching to Manual cancels the timer.
- Drink class/count is not used to decide whether a table duplicates the previous one. The same composition, such as two glasses of water, is processed again after a restart.
- With automatic restart off, the system waits for a manual Restart auto capture after serving ends. The waiting indicator is used only in this case; it does not mean the table was already handled.
- Stale Vision results that arrive after switching to Manual, a cancel, or a manual start are discarded using the mode epoch and the Controller token.
- The UI mode is managed in the Controller process, so it persists across new tabs and refreshes. On server restart, the environment defaults are applied again.

## Cost

The exact overlap area uses an x sweep + y segment tree: **O(n log n) time / O(n) memory**, with n≤50 by contract. Not every photo is stored; only the current best JPEG+VisionResult pair is kept (a single image is subject to the existing max_image_bytes limit).

2026-10-17, local Windows/Python 3.13 CPU, mean of 2,000 iterations each: 3 boxes **0.022ms**, 50 boxes **1.062ms**. This measures only the area calculation, excluding Vision inference, JPEG capture, and HTTP, and it is not a board measurement. Organizer-provided resident Vision performance follows separate records.

## Settings and contracts

```dotenv
CAPTURE_MODE=auto
AUTO_CAPTURE_INTERVAL_SECONDS=0.5
AUTO_CAPTURE_STABLE_SECONDS=3
AUTO_CAPTURE_RESTART_ENABLED=true
AUTO_CAPTURE_RESTART_SECONDS=10
OBSERVE_INTERVAL_SECONDS=0
```

The board `.env.board` defaults to Automatic (`CAPTURE_MODE=auto`) and starts automatic scanning when the server restarts. The development `.env.example` uses Manual. The mode can be changed in the UI, and on server restart the defaults of the selected env are applied again. The legacy OBSERVE_INTERVAL_SECONDS>0 setting is still honored as automatic-mode enablement/sample interval, but **the 3 s stability check also applies**. AUTO_CAPTURE_* is recommended for new settings.

- `GET /api/capture` → CaptureStatus
- `POST /api/capture`, JSON `{"mode":"auto"}` or `{"mode":"manual"}` → CaptureStatus. auto→auto is an explicit restart.
- `POST /api/capture/restart-timer`, JSON `{"enabled":true,"seconds":10}` → CaptureStatus. The setting and countdown are managed by the Controller and shared across refreshes and multiple tabs. On server restart, the env defaults are applied.
- `capture` is included in `/api/state` and the existing WS state.
- Separate WS event: `{"type":"capture","instance_id":"…","capture":{…}}`. Late responses are ignored using capture.revision. Progress does not increment the Controller sequence, so it does not invalidate the prompt-done ACK/Confirm.
- States: manual / scanning / stabilizing / paused / waiting / cooldown / error. `restart_remaining_seconds` has a value only while waiting. source=fixture is not real inference.

## Local verification

`tests/test_auto_capture.py`: area checked against an independent grid oracle and triple overlap; no start before 3 s; reset on class/count change, gap, and empty scene; best image and its result are identical with no re-inference; pause while serving and restart with the same composition; races between mode change/manual start/cancel and late results; error recovery and HTTP input validation.

Real Chrome `scripts/browser_auto_capture.cjs`: default 3 s automatic start, persistence across refresh, selected snapshot/bbox alignment, session preserved on mode change mid-flow, restart window reset, 1440/390px screens. This browser check used fixture Vision and is separate from real board camera accuracy/latency and real voice verification.

[2026-10-17 board deployment and real Vision sampling record](auto-capture-deployment-20261017.md).
