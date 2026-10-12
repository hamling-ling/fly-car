#include "motors.h"

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <Servo.h>

static const int RIGHT_MOTOR_PIN = 3;
static const int LEFT_MOTOR_PIN = 5;
static const unsigned long WATCHDOG_MS = 450;

// このシャーシは時計回りが反時計回りより速い。
// 反時計回り側だけ、1500 µs からの幅にこの倍率をかける。
// ラジコンの前進。速度 40 では 1.62、速度 67 では 1.17。一つの定数にはまとめていない。
static const double CCW_GAIN = 1.62;

static int offsetUs(int pulse, bool ccwWhenPositive) {
    double span = pulse / 255.0 * 500.0;
    bool ccw = ccwWhenPositive ? (pulse > 0) : (pulse < 0);
    if (ccw) {
        span *= CCW_GAIN;
    }
    return (int)span;
}

static Servo rightMotor;
static Servo leftMotor;
static unsigned long lastCommandMs = 0;
static int sentRight = 0;
static int sentLeft = 0;
static bool moving = false;

static void apply(int rightPulse, int leftPulse) {
    rightPulse = constrain(rightPulse, -255, 255);
    leftPulse = constrain(leftPulse, -255, 255);
    int leftUs = constrain(1500 - offsetUs(leftPulse, true), 1000, 2000);
    int rightUs = constrain(1500 + offsetUs(rightPulse, false), 1000, 2000);
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
