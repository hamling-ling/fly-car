#include "motors.h"

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <Servo.h>

static const int RIGHT_MOTOR_PIN = 3;
static const int LEFT_MOTOR_PIN = 5;
static const unsigned long WATCHDOG_MS = 450;

static Servo rightMotor;
static Servo leftMotor;
static unsigned long lastCommandMs = 0;
static int sentRight = 0;
static int sentLeft = 0;
static bool moving = false;

static void apply(int rightPulse, int leftPulse) {
    rightPulse = constrain(rightPulse, -255, 255);
    leftPulse = constrain(leftPulse, -255, 255);
    int leftUs = 1500 - (int)(leftPulse / 255.0 * 500);
    int rightUs = 1500 + (int)(rightPulse / 255.0 * 500);
    rightMotor.writeMicroseconds(rightUs);
    leftMotor.writeMicroseconds(leftUs);
    if (rightPulse == sentRight && leftPulse == sentLeft) {
        return;
    }
    sentRight = rightPulse;
    sentLeft = leftPulse;
    Monitor.print("setMotorSpeed L:");
    Monitor.print(leftPulse);
    Monitor.print(" R:");
    Monitor.println(rightPulse);
}

int setMotorSpeed(int rightPulse, int leftPulse) {
    apply(rightPulse, leftPulse);
    lastCommandMs = millis();
    moving = !(rightPulse == 0 && leftPulse == 0);
    return 0;
}

void motorsSetup() {
    rightMotor.attach(RIGHT_MOTOR_PIN);
    leftMotor.attach(LEFT_MOTOR_PIN);
    apply(0, 0);
    lastCommandMs = millis();
    moving = false;
}

void motorsLoop() {
    if (!moving) {
        return;
    }
    if (millis() - lastCommandMs < WATCHDOG_MS) {
        return;
    }
    apply(0, 0);
    moving = false;
    Monitor.println("watchdog stop");
}
