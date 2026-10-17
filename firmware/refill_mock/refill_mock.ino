// UNVERIFIED MCU DRAFT. No motors or gripper. Confirm LED polarity for the board.
#include <Arduino_RouterBridge.h>

enum Phase { IDLE=0, LOADING=1, RETURNING=2, DONE=3, CANCELLED=4 };
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
    if (now - lastPoll > 5000) phase = CANCELLED;  // lost host watchdog
    else if (now - startedAt >= 3000) phase = DONE;
    else if (now - startedAt >= 1500) phase = RETURNING;
  }
  // A running sequence owns the LED so it stays correct if the host goes away.
  // Otherwise the last set_led_state value persists, which is also the Bridge smoke test.
  bool running = (phase == LOADING || phase == RETURNING);
  applyLED(running ? true : manualLED);
  // No blocking sequence, nested Bridge.call(), or RPC logging in handlers.
}
