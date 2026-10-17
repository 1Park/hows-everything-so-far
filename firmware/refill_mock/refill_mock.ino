// UNVERIFIED MCU DRAFT. No motors or gripper. Confirm LED polarity for the board.
#include <Arduino_RouterBridge.h>

enum Phase { IDLE=0, LOADING=1, RETURNING=2, DONE=3, CANCELLED=4 };

// Mock sequence timings. The host polls refill_phase every mock_step_seconds
// (0.8s by default), so HOST_TIMEOUT_MS tolerates two missed polls and must stay
// below SEQUENCE_DONE_MS or the sequence would always finish before it can fire.
const unsigned long SEQUENCE_RETURNING_MS = 1500;
const unsigned long SEQUENCE_DONE_MS = 3000;
const unsigned long HOST_TIMEOUT_MS = 2000;
Phase phase = IDLE;
String lastCommand;
unsigned long startedAt = 0;
unsigned long lastPoll = 0;
// No sensor pins are guessed. Wire real inputs only after the team chooses hardware.
bool mockButton = false;
bool mockOccupied = false;
// Linux owns the LED except while a sequence runs; see loop().
bool manualLED = false;
int ledOutput = -1;  // -1 = never written, so the first apply always writes.

bool startMock(String command) {
  if (command.length() == 0 || command == lastCommand || phase == LOADING || phase == RETURNING) return false;
  lastCommand = command;
  startedAt = millis(); lastPoll = startedAt; phase = LOADING;
  return true;
}
bool cancelMock(String command) {
  // Tombstone prevents a delayed start RPC for the cancelled command from running.
  if (command.length() > 0) lastCommand = command;
  phase = CANCELLED;
  return true;
}
int readPhase() { lastPoll = millis(); return (int)phase; }
bool readButton() { return mockButton; }
bool readOccupied() { return mockOccupied; }
// RPC handler: record the request only. loop() decides what actually reaches the pin.
void setLED(bool on) { manualLED = on; }

// Active-low builtin LED; writes only on change.
void applyLED(bool on) {
  if (ledOutput == (int)on) return;
  ledOutput = (int)on;
  digitalWrite(LED_BUILTIN, on ? LOW : HIGH);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  applyLED(false);
  if (!Bridge.begin()) { while (true) { delay(10); } }
  Bridge.provide_safe("refill_start", startMock);
  Bridge.provide_safe("refill_cancel", cancelMock);
  Bridge.provide_safe("refill_phase", readPhase);
  Bridge.provide_safe("refill_button", readButton);
  Bridge.provide_safe("refill_occupied", readOccupied);
  Bridge.provide_safe("set_led_state", setLED);
}

void loop() {
  unsigned long now = millis();
  if (phase == LOADING || phase == RETURNING) {
    // Checked first: a host that stopped polling must stop the sequence even if
    // its remaining steps would otherwise complete.
    if (now - lastPoll > HOST_TIMEOUT_MS) phase = CANCELLED;
    else if (now - startedAt >= SEQUENCE_DONE_MS) phase = DONE;
    else if (now - startedAt >= SEQUENCE_RETURNING_MS) phase = RETURNING;
  }
  // A running sequence owns the LED so it stays correct if the host goes away.
  // Otherwise the last set_led_state value persists, which is also the Bridge smoke test.
  bool running = (phase == LOADING || phase == RETURNING);
  applyLED(running ? true : manualLED);
  // No blocking sequence, nested Bridge.call(), or RPC logging in handlers.
}
