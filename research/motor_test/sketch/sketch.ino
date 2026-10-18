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

// 左モーターの +/- は逆つなぎ。正の指令は左右とも 1500 µs より長くする。
// 反時計回りだけ広げる倍率は掛けない。
int spanUs(int pulse) {
    return (int)(pulse / 255.0 * 500.0);
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

    // 右はそのパルスで前進する。左は配線が逆なので、同じ側のパルスで前へ回る。
    int leftUs  = constrain(1500 + spanUs(leftPulse), 1000, 2000);
    int rightUs = constrain(1500 + spanUs(rightPulse), 1000, 2000);

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
