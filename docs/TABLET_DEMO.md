# Tablet and voice flow

The Controller owns the board camera and microphone, and the tablet browser owns the UI and speaker. The STT service accepts file input only. With `TTS_BACKEND=http`, prompts, greetings, and Replay voice all use board TTS. On failure it shows an error instead of falling back to the old WAVs. Fixed WAVs are used only when TTS is explicitly set to disabled in development.

## Connecting and using

1. Start the services with the [board runbook](BOARD_RUNBOOK.md) and open `http://<board-address>:8080/` on the tablet. External access requires `CONTROLLER_HOST=0.0.0.0`.
2. Enable the speaker with Enable sound. It may be needed again after a refresh.
3. Observe with Start demo or [Automatic capture](AUTO_CAPTURE.md). Automatic mode starts only after the per-class object counts stay the same for 3 s by default. After serving ends, it restarts automatically after 10 s by default; the wait time can be changed or the timer disabled in Demo tools.
4. When the target suggestion prompt ends, the browser ACKs with the current session/scene/object/sequence. Muted, failed, or cancelled prompts do not start recording.
5. The board records for the configured time → STT → LLM → card. The UI changes LISTENING → TRANSCRIBING → INTERPRETING → CARD. There is no VAD; the recording length is `AUDIO_SECONDS`.
6. Check the transcript and drink, then edit and Confirm, or Cancel. LLM `not_understood` and STT `no_speech`/timeout switch to a re-ask state; when the prompt finishes playing, the browser ACKs the current state and board recording restarts automatically. No automatic recording after a cancel, scene change, mute, or playback failure. Other service failures are retried manually from the error state. A card alone never starts the hardware.

On a network disconnect, input is blocked, and the latest state is restored after reconnecting. Restarting auto capture restarts the stability window. Manual start, mode switch, and same-table restart rules follow the auto capture document.

## Audio settings

`.env.board` uses `AUDIO_INPUT=alsa`, the B101 device, S16_LE/16kHz/mono/4 s. When replacing the device, check `arecord -l` and the supported formats, then set `AUDIO_DEVICE/FORMAT/RATE/CHANNELS/SECONDS`. Board recording does not need tablet microphone permission or HTTPS.

With `AUDIO_INPUT=disabled`, development browser recording, transcript review, and Send are provided. Run over HTTPS or localhost to use the browser microphone. `AUDIO_INPUT=fixture` generates a silent WAV for tests.

For board-free verification of prompt end → recording → card, follow the [validation commands](VALIDATION.md). Fixture and virtual microphone results are not real microphone accuracy or speaker listening verification.
