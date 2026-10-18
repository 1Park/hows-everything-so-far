# Browser UI

The Controller serves HTML/CSS/JS at `/`. `/dashboard` shows mock and live event history; `/stt` is a transcription accuracy measurement tool.

The board owns the camera and microphone; the browser owns the UI and speaker. After a TTS prompt finishes, the flow goes ACK → board recording → STT → LLM → card. Enable sound is required the first time. With `TTS_BACKEND=http`, the welcome message and Replay voice also use TTS; on failure an error is shown and the old WAV is not used as a fallback. Fixed WAVs are used only with the dev setting `TTS_BACKEND=disabled`. With `AUDIO_INPUT=disabled`, dev browser recording, transcript review and Send are provided.

State arrives over WS, and late responses are ignored using instance_id/sequence. The analysis snapshot is shown together with bboxes and kept distinct from the live preview. Capture mode and stability progress are updated through separate capture events. Confirm is only possible on the current card.

The Controller `/health` is checked every 1 second with a 2-second limit per request. When the connection drops,
a `bad cable connection` notice is shown and input and recording are blocked. When the connection returns,
the notice closes after the latest state is received over a new WebSocket, and the video reconnects too. The page
is not reloaded and previous requests are not resent automatically. The browser cannot distinguish cable, network
and server outages, so the same notice is used for all of them.

Reconnect check: run a separate offline server on port 8096, then `npm run test:reconnect`.

**Enable untrained drink variants (demo only)** in Demo tools is OFF by default.
When ON, water/sparkling water/soda can be chosen for a water observation, and coke/coke zero/coffee for a coke
observation. This does not mean the extra types were identified from the image; the customer's utterance and the LLM choose them.
It resets to OFF on server restart; on page reload the current server setting is kept.
Changing the option discards the existing card. The fixed category mapping itself is read-only.
Check: `node scripts/browser_categories.cjs` against an offline server (default port 8088).

[Capture modes](../../docs/AUTO_CAPTURE.md), [Tablet use](../../docs/TABLET_DEMO.md), [Browser validation](../../docs/VALIDATION.md).
