// Mock sequence only: no motors or gripper. Run on QCVENTUNO002 2026-10-18 —
// all six RPCs answered, LED1 showed white and each RGB channel, the sequence
// stepped LOADING/RETURNING/DONE at 1.5s and 3s, a duplicate command id and a
// late start after cancel were refused, and 3s without a poll cancelled it.
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
// Linux decides the colour; this sketch only applies it. Keeping the mapping on
// the host means new states need no firmware change.
bool manualLED = false;
int manualR = 0, manualG = 0, manualB = 0;
int outR = -1, outG = -1, outB = -1;  // -1 = never written, so the first apply writes.

// Colour the sequence shows while it runs, independent of whatever Linux last set.
const int RUNNING_R = 0, RUNNING_G = 0, RUNNING_B = 255;

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
// RPC handlers: record the request only. loop() decides what reaches the pins.
// Plain on/off stays available as the Bridge smoke test and shows white.
void setLED(bool on) {
  manualLED = on;
  manualR = manualG = manualB = on ? 255 : 0;
}

bool setLEDColor(int r, int g, int b) {
  if (r < 0 || r > 255 || g < 0 || g > 255 || b < 0 || b > 255) return false;
  manualR = r; manualG = g; manualB = b;
  manualLED = (r || g || b);
  return true;
}

// Active-low RGB channels; writes only on change.
void applyLED(int r, int g, int b) {
  if (outR == r && outG == g && outB == b) return;
  outR = r; outG = g; outB = b;
  analogWrite(LED1_R, 255 - r);
  analogWrite(LED1_G, 255 - g);
  analogWrite(LED1_B, 255 - b);
}

void setup() {
  pinMode(LED1_R, OUTPUT);
  pinMode(LED1_G, OUTPUT);
  pinMode(LED1_B, OUTPUT);
  applyLED(0, 0, 0);
  if (!Bridge.begin()) { while (true) { delay(10); } }
  Bridge.provide_safe("refill_start", startMock);
  Bridge.provide_safe("refill_cancel", cancelMock);
  Bridge.provide_safe("refill_phase", readPhase);
  Bridge.provide_safe("refill_button", readButton);
  Bridge.provide_safe("refill_occupied", readOccupied);
  Bridge.provide_safe("set_led_state", setLED);
  Bridge.provide_safe("set_led_color", setLEDColor);
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
  if (running) applyLED(RUNNING_R, RUNNING_G, RUNNING_B);
  else applyLED(manualR, manualG, manualB);
  // No blocking sequence, nested Bridge.call(), or RPC logging in handlers.
}
