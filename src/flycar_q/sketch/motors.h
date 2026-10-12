#pragma once

// rightPulse / leftPulse は -255〜255。正が前進、0 が停止。
int setMotorSpeed(int rightPulse, int leftPulse);
void motorsSetup();
void motorsLoop();
