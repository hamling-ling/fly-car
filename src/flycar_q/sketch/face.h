#pragma once

#include <vector>

// 起動時の 1 点は、後ろから見て前の左。showFace は長さ 104 の 0/1。
// showLamps は検知と車輪の色。最後の更新から 450 ms で絵もランプも消す。
void faceSetup();
void faceLoop();
void showFace(std::vector<int> levels);
void showLamps(int seeRed, int seeBlue, int goForward, int goBack);
