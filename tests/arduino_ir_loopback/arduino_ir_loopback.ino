/*
 * Elixpo Badge — IR hardware loopback test
 *
 * Validates IR LED transmitter + TSOP1738 receiver are both functional
 * by sending an NEC code every second and decoding what comes back.
 *
 * Hardware: Arduino Nano (or Uno — same pin map for Timer2)
 * Library:  IRremote v4.x by Armin Joachimsmeyer
 *           (Tools → Manage Libraries → search "IRremote" → install latest)
 *
 * If you see "TX → ... | RX ← addr=0x12 cmd=0xNN" matching pairs in serial,
 * both halves of the IR subsystem are working. You can then trust the same
 * components when wiring them to the ESP32-S3.
 */

#include <IRremote.hpp>

// ---- Pin assignments ----
// Pin 3 is fixed: IRremote uses Timer2, OC2B output = Arduino Pin 3 on Nano/Uno
#define IR_SEND_PIN     3
// Pin 2 supports external interrupt (not required by v4 but good practice)
#define IR_RECEIVE_PIN  2

// ---- Test parameters ----
const uint16_t NEC_ADDRESS = 0x12;
const unsigned long SEND_INTERVAL_MS = 1000;

uint8_t cmd = 0x00;
unsigned long lastSend = 0;
unsigned long txCount = 0;
unsigned long rxCount = 0;

void setup() {
  Serial.begin(9600);
  while (!Serial) {} // wait for native USB if applicable

  Serial.println();
  Serial.println(F("=== Elixpo IR Loopback Test ==="));
  Serial.print(F("TX pin: D")); Serial.println(IR_SEND_PIN);
  Serial.print(F("RX pin: D")); Serial.println(IR_RECEIVE_PIN);
  Serial.println(F("Sending NEC every 1s. Watch for matching RX lines."));
  Serial.println();

  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK); // onboard LED blinks on RX
  IrSender.begin(IR_SEND_PIN);
}

void loop() {
  // ---- Periodic TX ----
  if (millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();
    txCount++;

    Serial.print(F("TX → addr=0x"));
    Serial.print(NEC_ADDRESS, HEX);
    Serial.print(F(" cmd=0x"));
    if (cmd < 0x10) Serial.print('0');
    Serial.print(cmd, HEX);
    Serial.print(F("  (#"));
    Serial.print(txCount);
    Serial.println(F(")"));

    IrSender.sendNEC(NEC_ADDRESS, cmd, 0 /* no repeats */);
    cmd++;
  }

  // ---- RX decode ----
  if (IrReceiver.decode()) {
    rxCount++;
    Serial.print(F("RX ← "));
    Serial.print(F("proto="));
    Serial.print(getProtocolString(IrReceiver.decodedIRData.protocol));
    Serial.print(F(" addr=0x"));
    Serial.print(IrReceiver.decodedIRData.address, HEX);
    Serial.print(F(" cmd=0x"));
    Serial.print(IrReceiver.decodedIRData.command, HEX);
    Serial.print(F("  (#"));
    Serial.print(rxCount);
    Serial.print(F(", success rate "));
    Serial.print((100UL * rxCount) / (txCount ? txCount : 1));
    Serial.println(F("%)"));

    IrReceiver.resume();
  }
}
