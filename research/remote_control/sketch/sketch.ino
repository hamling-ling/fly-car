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

// 起動時の倍率。ページのスライダが setCcwGain で上書きする。
// 1620 は 1.62 倍。前進、速度 40 のときの値。速度 67 では 1.17 だった。
// 速度で変わるので、これ以上は一つの定数にまとめない。
// 反時計回り側だけ、1500 µs からの幅にかける。
const int CCW_GAIN_MILLI = 1620;

double ccwGain = CCW_GAIN_MILLI / 1000.0;
int lastRightPulse = 0;
int lastLeftPulse = 0;

int offsetUs(int pulse, bool ccwWhenPositive) {
    double span = pulse / 255.0 * 500.0;
    bool ccw = ccwWhenPositive ? (pulse > 0) : (pulse < 0);
    if (ccw) {
        span *= ccwGain;
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
    lastRightPulse = rightPulse;
    lastLeftPulse = leftPulse;

    LOG_MONITOR("setMotorSpeed L:%d(%dus) R:%d(%dus)", leftPulse, leftUs, rightPulse, rightUs);

    return MCU_RESULT::MCU_SUCCESS;
}

// milli は 1000 が 1.00 倍、2000 が 2.00 倍。今の指令を掛け直す。
int setCcwGain(int milli) {
    if (milli < 1000) milli = 1000;
    if (milli > 2000) milli = 2000;
    ccwGain = milli / 1000.0;
    LOG_MONITOR("ccw gain %d.%03d", milli / 1000, milli % 1000);
    return setMotorSpeed(lastRightPulse, lastLeftPulse);
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
    Bridge.provide("setCcwGain", setCcwGain);

    Monitor.println("Motor ready");
}

void loop() {
    // Bridge経由で呼ばれるだけなので空でOK
}
