#include <Arduino_RouterBridge.h>

#include "motors.h"

void setup() {
    Monitor.begin(115200);
    delay(100);
    motorsSetup();
    Bridge.begin();
    Bridge.provide("setMotorSpeed", setMotorSpeed);
    Monitor.println("Motor ready");
}

void loop() {
    motorsLoop();
}
