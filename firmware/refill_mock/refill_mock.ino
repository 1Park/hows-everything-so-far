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
void setLED(bool on) { digitalWrite(LED_BUILTIN, on ? LOW : HIGH); }

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  setLED(false);
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
  setLED(phase == LOADING || phase == RETURNING);
  // No blocking sequence, nested Bridge.call(), or RPC logging in handlers.
}
