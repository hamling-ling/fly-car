#include "motors.h"

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <Servo.h>

#include "face.h"

static const int RIGHT_MOTOR_PIN = 3;
static const int LEFT_MOTOR_PIN = 5;
static const unsigned long WATCHDOG_MS = 450;

// 左モーターの +/- は逆つなぎ。正の指令は左右とも 1500 µs より長くする。
// 反時計回りだけ広げる倍率は掛けない。
static int spanUs(int pulse) {
    return (int)(pulse / 255.0 * 500.0);
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
    // 右はそのパルスで前進する。左は配線が逆なので、同じ側のパルスで前へ回る。
    int leftUs = constrain(1500 + spanUs(leftPulse), 1000, 2000);
    int rightUs = constrain(1500 + spanUs(rightPulse), 1000, 2000);
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
    faceLoop();
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
