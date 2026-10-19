#include <Arduino_RouterBridge.h>

#include "face.h"
#include "motors.h"

void setup() {
    Monitor.begin(115200);
    delay(100);
    motorsSetup();
    faceSetup();
    Bridge.begin();
    Bridge.provide("setMotorSpeed", setMotorSpeed);
    Bridge.provide("showFace", showFace);
    Bridge.provide("showLamps", showLamps);
    Monitor.println("Motor ready");
}

void loop() {
    motorsLoop();
}
