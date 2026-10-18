# Auto capture deployment record

These are verification results from that time; for current operation, follow the [board runbook](BOARD_RUNBOOK.md).

## Board deployment check (2026-10-17 Pacific)

Feature commit `1ac6e0a` and the merge of the team's latest changes `b2de6a0` were applied to QCVENTUNO002. After the merge, 49 Controller/HTTP/auto capture/board voice/Vision tests and Ruff passed.

- The existing direct + with-stt supervisor was restarted after waiting for it to stop completely. Gemma4/Whisper were not restarted.
- Before deployment, the Vision service was found to have failed to start because the worker path was missing. It was recovered with the existing runbook's `dinov2-qnn-v4c`, the real `qnn_vision_worker`, and the QNN library settings. The model/preprocessing was not changed.
- Confirmed Controller `/ready`=true, Vision/STT source=external, LLM source=executorch, and Gemma4 resident=true.
- Automatic mode was turned on for under 5 s to confirm periodic real camera→Vision calls (source=external), then restored to Manual. At that time 0 objects were detected, so it stayed in the scanning state and did not start a session, recording, or hardware action. A full demo with real cups placed (5 s stability → prompt) still needs a separate on-site check.
- Runtime logs/verification results: board `logs/dev-8080.out`, `logs/controller.log`, `logs/auto-capture-deploy-check.json`. On the tablet, refresh http://192.168.50.1:8080/ and select Capture mode → Automatic.
