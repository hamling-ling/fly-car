#include "face.h"

#include <Arduino.h>
#include <Arduino_LED_Matrix.h>

static const int FACE_PIXELS = 104;
static const unsigned long FACE_BLANK_MS = 450;

static Arduino_LED_Matrix matrix;
static unsigned long lastFaceMs = 0;
static bool live = false;

static void writeLamp(int pin, int on) {
    digitalWrite(pin, on ? LOW : HIGH);
}

static void lampsOff() {
    writeLamp(LED3_R, 0);
    writeLamp(LED3_G, 0);
    writeLamp(LED3_B, 0);
    writeLamp(LED4_R, 0);
    writeLamp(LED4_G, 0);
    writeLamp(LED4_B, 0);
}

static void lampsSetup() {
    const int pins[] = {LED3_R, LED3_G, LED3_B, LED4_R, LED4_G, LED4_B};
    for (int pin : pins) {
        pinMode(pin, OUTPUT);
    }
    lampsOff();
}

void faceSetup() {
    matrix.begin();
    matrix.setGrayscaleBits(1);
    lampsSetup();
    uint8_t frame[FACE_PIXELS] = {};
    // 行 7・列 12。基板の下辺が前で、後ろから見た左前。
    frame[7 * 13 + 12] = 1;
    matrix.draw(frame);
}

void showFace(std::vector<int> levels) {
    if (levels.size() != static_cast<size_t>(FACE_PIXELS)) {
        return;
    }
    uint8_t frame[FACE_PIXELS];
    for (int i = 0; i < FACE_PIXELS; ++i) {
        frame[i] = levels[i] > 0 ? 1 : 0;
    }
    matrix.draw(frame);
    lastFaceMs = millis();
    live = true;
}

void showLamps(int seeRed, int seeBlue, int goForward, int goBack) {
    // LED3 は見えている色、LED4 は車輪。赤の検知と前進が赤、青と後退が青。
    writeLamp(LED3_R, seeRed);
    writeLamp(LED3_G, 0);
    writeLamp(LED3_B, seeBlue);
    writeLamp(LED4_R, goForward);
    writeLamp(LED4_G, 0);
    writeLamp(LED4_B, goBack);
    lastFaceMs = millis();
    live = true;
}

void faceLoop() {
    if (!live) {
        return;
    }
    if (millis() - lastFaceMs < FACE_BLANK_MS) {
        return;
    }
    uint8_t frame[FACE_PIXELS] = {};
    matrix.draw(frame);
    lampsOff();
    live = false;
}
