#include <Arduino_RouterBridge.h>
#include <Servo.h>

// ログ出力マクロの定義（1ステップでバッファ作成から出力まで行います）
#define LOG_MONITOR(format, ...) do { \
    char _log_buf[128]; \
    snprintf(_log_buf, sizeof(_log_buf), format, ##__VA_ARGS__); \
    Monitor.println(_log_buf); \
} while(0)


Servo rightMotor;
Servo leftMotor;

const int RIGHT_MOTOR_PIN = 3;
const int LEFT_MOTOR_PIN  = 5;

// このシャーシは時計回りが反時計回りより速い。
// 反時計回り側だけ、1500 µs からの幅にこの倍率をかける。
// ラジコンの前進。速度 40 では 1.62、速度 67 では 1.17。一つの定数にはまとめていない。
const double CCW_GAIN = 1.62;

int offsetUs(int pulse, bool ccwWhenPositive) {
    double span = pulse / 255.0 * 500.0;
    bool ccw = ccwWhenPositive ? (pulse > 0) : (pulse < 0);
    if (ccw) {
        span *= CCW_GAIN;
    }
    return (int)span;
}

enum MCU_RESULT : int {
    MCU_SUCCESS = 0,
    MCU_ERROR = -1
};

/**
 * モーター速度設定
 * rightPulse / leftPulse: -255〜255
 *   負 = 後退、正 = 前進、0 = 停止
 * 内部で 1000〜2000 µs に変換（1500が停止）
 */
int setMotorSpeed(int rightPulse, int leftPulse) {
    // 範囲制限
    rightPulse = constrain(rightPulse, -255, 255);
    leftPulse  = constrain(leftPulse,  -255, 255);

    // 左の前進は CCW、右の前進は CW。端は 1000〜2000 µs。
    int leftUs  = constrain(1500 - offsetUs(leftPulse, true), 1000, 2000);
    int rightUs = constrain(1500 + offsetUs(rightPulse, false), 1000, 2000);

    rightMotor.writeMicroseconds(rightUs);
    leftMotor.writeMicroseconds(leftUs);

    LOG_MONITOR("setMotorSpeed L:%d(%dus) R:%d(%dus)", leftPulse, leftUs, rightPulse, rightUs);

    return MCU_RESULT::MCU_SUCCESS;
}

void setup() {
    Monitor.begin(115200);
    delay(100);  // Monitor安定待ち

    rightMotor.attach(RIGHT_MOTOR_PIN);
    leftMotor.attach(LEFT_MOTOR_PIN);

    // 初期状態は停止
    setMotorSpeed(0, 0);

    Bridge.begin();
    Bridge.provide("setMotorSpeed", setMotorSpeed);

    Monitor.println("Motor ready");
}

void loop() {
    // Bridge経由で呼ばれるだけなので空でOK
}
