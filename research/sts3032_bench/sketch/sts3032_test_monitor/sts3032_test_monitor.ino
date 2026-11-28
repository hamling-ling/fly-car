// STS3032 テストスケッチ（Monitor 版）— Arduino UNO Q（MCU 側）
// 作成: 2026-11-28。ベンチ計画 sts3032-bench-plan.md の項目 0–4 を
// UNO Q の Serial1（D0/D1）→ FE-URT2 の UART ヘッダ経由で回すためのもの。
// 元の sts3032_test.ino との差分はコンソール入出力だけ（Serial -> Monitor）。
// バス側の Serial1、パケット層、レジスタ表、RPM 換算、コマンドは無変更。
//
// 【なぜ Monitor 版か】UNO Q のボードプラットフォーム 0.55.0 で Serial の
// 意味が変わった。0.55.0 より前は Serial = D0/D1 の UART で、App Lab の
// コンソールには Monitor が必要だった。0.55.0 からは Serial がコンソールの
// 別名になり、D0/D1 は Serial1 になった。元のスケッチ（コンソール Serial、
// バス Serial1）は 0.55.0 以降でのみ正しく、古い版だと「起動メッセージも
// 出ず、p を打っても完全無応答」になる。Monitor 版はコンソール経路について
// プラットフォームの版に依存しない。
// 【バス側の前提】バスが Serial1 なのは 0.55.0 以降の前提。もしプラット
// フォームがそれより古い場合、バスは Serial 側になる。その場合はこの
// ファイル中の Serial1 をすべて Serial に置き換える（コンソール側の
// Monitor はそのまま）。
// 【2026-11-28 17:00 JST 実測で確定】Serial バス変種でパケットがモニタに流れて
// 文字化けしたので、この環境は 0.55.0 以降の割り当て（Serial = コンソール、
// バス = Serial1）で確定。この Monitor 版が正解のスケッチ。
//
// 配線（2026-11-28 訂正）:
//   URT-2 TX -> UNO Q D1 (TX), URT-2 RX -> UNO Q D0 (RX),
//   URT-2 V -> UNO Q 5V, GND 共通。
//   FEETECH の URT-2 配線ガイドどおり「TX-TX, RX-RX, V-V, G-G」。
//   ヘッダの V は USB 未接続時に URT 基板側の変換回路へ給電するための入力で、
//   サーボ電源（ネジ端子 6 V）とは別系統。同時に繋ぐのが公式の構成
//   （秋月の FEETECH 説明書も URT-1 + Arduino で +5V 接続を明記）。
//   レベル切替スイッチは信号レベルの選択で、UNO Q では 3.3 V 側。
//   URT-2 の USB は PC に繋がない（モードはどちらか一方）。
//
// 使い方: App Lab のシリアルモニタから1文字コマンドを送る。
// 注意: こちらではコンパイル検証ができていないので、確認は App Lab の
// コンパイルが兼ねる。
//   p : ping（ID 1）
//   i : 情報読み取り（MODE / 電圧 / 温度 / 位置 / 速度 / 負荷）※回らない
//   1 : 速度閉ループ（モード 1）に設定する（EEPROM 書き込み）
//   T : トルク ON    t : トルク OFF
//   q : +16 RPM で 3 秒（項目 2 の低速確認）
//   r : +48 RPM で 3 秒（項目 1/3。回転中に指で軸を押さえると項目 3）
//   b : -16 RPM で 3 秒（項目 4 の後進対称）
//   s : 停止（目標速度 0）
// 回転中は Present Speed を 200 ms ごとに表示する。回転中に何かキーを
// 送るとその場で止まる。setup() ではトルクを入れないので、電源投入だけでは
// 絶対に回らない。
//
// プロトコル: FEETECH SCS/STS 共通パケット（FF FF ID LEN CMD ... CHK）。
// レジスタは sts3032_bench.py と同じ照合済みマップ。
// 速度の単位は steps/s（4096 steps/回転、48 RPM = 3277）。
// 後進は sign-magnitude（bit 15 が符号、-48 RPM = 36045）。
// Present Speed の読みは 50 steps/s 刻み（48 RPM で ±0.8%）。

#include <Arduino.h>
#include <Arduino_RouterBridge.h>  // Monitor オブジェクト用（App Lab のモニタ）

// ---- レジスタ（STS 系共通マップ、4 系統で照合済み） ----
static const uint8_t ADDR_MODE            = 33;  // EEPROM。1 = 速度閉ループ
static const uint8_t ADDR_TORQUE_ENABLE   = 40;
static const uint8_t ADDR_GOAL_SPEED      = 46;  // 2 バイト
static const uint8_t ADDR_LOCK            = 55;  // EEPROM ロック（0=解除, 1=ロック）
static const uint8_t ADDR_PRESENT_POS     = 56;  // 2 バイト（出荷時は 1 回転で折り返す）
static const uint8_t ADDR_PRESENT_SPEED   = 58;  // 2 バイト、sign-magnitude
static const uint8_t ADDR_PRESENT_VOLTAGE = 62;  // 1 バイト、×0.1 V
static const uint8_t ADDR_PRESENT_TEMP    = 63;  // 1 バイト、℃
static const uint8_t ADDR_PRESENT_LOAD    = 60;  // 2 バイト。bit10=符号、0–1000 が 0.1%
// 注: STS3032 に電流フィードバックは無く、addr 69 は常に 0 を返す（2026-11-28 実測）。
// 負荷（トルク相当）はこちらの Present Load で見る。

static const uint8_t SERVO_ID = 1;               // 起動時の宛先 ID
static uint8_t targetId = SERVO_ID;  // 'd'+数字コマンドで実行時に変更できる
static const long    BUS_BAUD = 1000000;         // STS デフォルト
static const long    STEPS_PER_REV = 4096;

// ---- パケット層 ----
static const uint8_t INST_PING  = 0x01;
static const uint8_t INST_READ  = 0x02;
static const uint8_t INST_WRITE = 0x03;

// 【バグ修正 2026-11-28】初版にあった「エコーバック捨て」処理は削除した。
// URT-2 のヘッダは TX/RX 別線なのでエコーは構造的に返らない。それどころか
// あの処理は応答の先頭（FF FF ID LEN は送信パケットと共通）をエコーと
// 誤認して食べてしまい、readStatus がヘッダを見つけられず全読み取りが
// タイムアウトしていた。これが ping 無応答の原因。
static int readBusByte(unsigned long timeoutMs) {
  unsigned long t0 = millis();
  while (millis() - t0 < timeoutMs) {
    int c = Serial1.read();
    if (c >= 0) return c;
  }
  return -1;
}

static void sendPacket(uint8_t id, uint8_t inst, const uint8_t *params, uint8_t nParams) {
  uint8_t len = nParams + 2;
  uint8_t pkt[20];
  pkt[0] = 0xFF; pkt[1] = 0xFF; pkt[2] = id; pkt[3] = len; pkt[4] = inst;
  uint8_t sum = id + len + inst;
  for (uint8_t i = 0; i < nParams; i++) { pkt[5 + i] = params[i]; sum += params[i]; }
  pkt[5 + nParams] = (uint8_t)~sum;
  uint8_t total = 5 + nParams + 1;
  // 受信バッファの残りを捨ててから送る
  while (Serial1.available()) Serial1.read();
  Serial1.write(pkt, total);
  Serial1.flush();
}

// 応答パケットを読む。成功したら err と params を返す。
static bool readStatus(uint8_t expectId, uint8_t *errOut,
                       uint8_t *paramsOut, uint8_t *nParamsOut,
                       unsigned long timeoutMs = 100) {
  unsigned long t0 = millis();
  // ヘッダ FF FF を探す
  int prev = -1;
  while (millis() - t0 < timeoutMs) {
    int c = readBusByte(timeoutMs - (millis() - t0));
    if (c < 0) return false;
    if (prev == 0xFF && c == 0xFF) break;
    prev = c;
  }
  int id = readBusByte(50);
  int len = readBusByte(50);
  if (id < 0 || len < 0 || len < 2 || len > 12) return false;
  if (id != expectId) return false;
  uint8_t body[14];
  body[0] = (uint8_t)id; body[1] = (uint8_t)len;
  for (int i = 0; i < len; i++) {
    int c = readBusByte(50);
    if (c < 0) return false;
    body[2 + i] = (uint8_t)c;  // body[2]=ERR, 以後 params, 最後が CHK
  }
  uint8_t sum = 0;
  for (int i = 0; i < 2 + len - 1; i++) sum += body[i];
  if ((uint8_t)~sum != body[2 + len - 1]) return false;
  *errOut = body[2];
  *nParamsOut = len - 2;
  for (int i = 0; i < len - 2; i++) paramsOut[i] = body[3 + i];
  return true;
}

static bool pingServo(uint8_t id) {
  sendPacket(id, INST_PING, nullptr, 0);
  uint8_t err, params[12], n;
  return readStatus(id, &err, params, &n);
}

static bool readBytes(uint8_t id, uint8_t addr, uint8_t nRead, uint8_t *out) {
  uint8_t params[2] = {addr, nRead};
  sendPacket(id, INST_READ, params, 2);
  uint8_t err, buf[12], n;
  if (!readStatus(id, &err, buf, &n)) return false;
  if (err != 0 || n < nRead) return false;
  memcpy(out, buf, nRead);
  return true;
}

static bool read1(uint8_t id, uint8_t addr, uint8_t *out) {
  return readBytes(id, addr, 1, out);
}

static bool read2(uint8_t id, uint8_t addr, uint16_t *out) {
  uint8_t b[2];
  if (!readBytes(id, addr, 2, b)) return false;
  *out = b[0] | ((uint16_t)b[1] << 8);
  return true;
}

// 書き込みへの応答はリターンレベル既定では返らないので待たない。
static void writeBytes(uint8_t id, uint8_t addr, const uint8_t *data, uint8_t nData) {
  uint8_t params[10];
  params[0] = addr;
  memcpy(params + 1, data, nData);
  sendPacket(id, INST_WRITE, params, nData + 1);
  delay(5);
}

static void write1(uint8_t id, uint8_t addr, uint8_t v) { writeBytes(id, addr, &v, 1); }

static void write2(uint8_t id, uint8_t addr, uint16_t v) {
  uint8_t b[2] = {(uint8_t)(v & 0xFF), (uint8_t)(v >> 8)};
  writeBytes(id, addr, b, 2);
}

// ---- 速度換算（sts3032_bench.py と同じ） ----
static uint16_t rpmToGoal(float rpm) {
  long steps = lroundf(fabsf(rpm) / 60.0f * (float)STEPS_PER_REV);
  if (rpm < 0) return (uint16_t)(0x8000 | (uint16_t)steps);
  return (uint16_t)steps;
}

static float rawToRpm(uint16_t raw) {
  float rpm = (float)(raw & 0x7FFF) / (float)STEPS_PER_REV * 60.0f;
  return (raw & 0x8000) ? -rpm : rpm;
}

// ---- コマンド実装 ----
static void cmdPing() {
  Monitor.print(F("ping ID "));
  Monitor.print(targetId);
  Monitor.println(pingServo(targetId) ? F(" -> OK") : F(" -> 応答なし"));
}

static void cmdInfo() {
  uint8_t mode, volt, temp;
  uint16_t pos, spd, loadRaw;
  bool ok = true;
  ok &= read1(targetId, ADDR_MODE, &mode);
  ok &= read1(targetId, ADDR_PRESENT_VOLTAGE, &volt);
  ok &= read1(targetId, ADDR_PRESENT_TEMP, &temp);
  ok &= read2(targetId, ADDR_PRESENT_POS, &pos);
  ok &= read2(targetId, ADDR_PRESENT_SPEED, &spd);
  ok &= read2(targetId, ADDR_PRESENT_LOAD, &loadRaw);
  if (!ok) { Monitor.println(F("読み取り失敗（応答なし／チェックサム不一致）")); return; }
  float loadPct = (float)(loadRaw & 0x3FF) / 10.0f;
  if (loadRaw & 0x0400) loadPct = -loadPct;
  Monitor.print(F("MODE=")); Monitor.print(mode);
  Monitor.print(F("（1=速度閉ループ） 電圧=")); Monitor.print(volt / 10.0f, 1);
  Monitor.print(F(" V 温度=")); Monitor.print(temp);
  Monitor.print(F(" C 位置=")); Monitor.print(pos);
  Monitor.print(F(" 速度=")); Monitor.print(rawToRpm(spd), 1);
  Monitor.print(F(" RPM 負荷=")); Monitor.print(loadPct, 1);
  Monitor.println(F(" %"));
}

static void cmdSetModeSpeed() {
  // EEPROM 書き込み: トルク OFF -> ロック解除 -> MODE=1 -> ロック
  write1(targetId, ADDR_TORQUE_ENABLE, 0);
  write1(targetId, ADDR_LOCK, 0);
  write1(targetId, ADDR_MODE, 1);
  write1(targetId, ADDR_LOCK, 1);
  delay(20);
  uint8_t mode;
  if (read1(targetId, ADDR_MODE, &mode)) {
    Monitor.print(F("MODE を読み戻し: "));
    Monitor.println(mode);
    if (mode != 1) Monitor.println(F("注意: 1 になっていません。ロック解除が要る個体かもしれません"));
  } else {
    Monitor.println(F("MODE の読み戻しに失敗"));
  }
}

static void stopServo() {
  write2(targetId, ADDR_GOAL_SPEED, 0);
}

static void cmdRun(float rpm, unsigned long seconds) {
  write1(targetId, ADDR_TORQUE_ENABLE, 1);
  uint16_t goal = rpmToGoal(rpm);
  write2(targetId, ADDR_GOAL_SPEED, goal);
  Monitor.print(F("指令 "));
  Monitor.print(rpm, 0);
  Monitor.print(F(" RPM (GOAL_SPEED="));
  Monitor.print(goal);
  Monitor.print(F(") を "));
  Monitor.print(seconds);
  Monitor.println(F(" 秒。何かキーを送ると止まります"));
  // コマンド送信に付いてきた改行などを先に読み捨てる（これを止まる条件に
  // すると、q を送った直後に同梱の改行で即停止してしまう。2026-11-28 実測）
  while (Monitor.available()) { (void)Monitor.read(); }
  unsigned long t0 = millis();
  while (millis() - t0 < seconds * 1000UL) {
    bool stopKey = false;
    while (Monitor.available()) {
      char k = (char)Monitor.read();
      if (k != '\n' && k != '\r') stopKey = true;
    }
    if (stopKey) break;
    uint16_t spd;
    if (read2(targetId, ADDR_PRESENT_SPEED, &spd)) {
      Monitor.print(F("  現在速度 "));
      Monitor.print(rawToRpm(spd), 1);
      Monitor.println(F(" RPM"));
    } else {
      Monitor.println(F("  速度の読み取り失敗"));
    }
    delay(200);
  }
  stopServo();
  Monitor.println(F("停止しました"));
}

static void printHelp() {
  Monitor.println(F("STS3032 テスト: p=ping i=情報 1=速度閉ループに設定"));
  Monitor.println(F("T=トルクON t=トルクOFF q=+16RPM r=+48RPM b=-16RPM s=停止"));
  Monitor.println(F("d+数字=宛先ID変更（例: d2 で ID 2 宛て）"));
}

void setup() {
  Monitor.begin();
  Serial1.begin(BUS_BAUD);
  delay(500);
  printHelp();
  cmdPing();  // 接続確認だけ。トルクは入れない。
}

void loop() {
  if (!Monitor.available()) return;
  char c = (char)Monitor.read();
  static bool awaitId = false;
  if (awaitId) {
    awaitId = false;
    if (c >= '0' && c <= '9') {
      targetId = (uint8_t)(c - '0');
      Monitor.print(F("宛先 ID = "));
      Monitor.println(targetId);
    }
    return;
  }
  switch (c) {
    case 'd': awaitId = true; Monitor.println(F("ID の数字を送ってください")); break;
    case 'p': cmdPing(); break;
    case 'i': cmdInfo(); break;
    case '1': cmdSetModeSpeed(); break;
    case 'T': write1(targetId, ADDR_TORQUE_ENABLE, 1); Monitor.println(F("トルク ON")); break;
    case 't': write1(targetId, ADDR_TORQUE_ENABLE, 0); Monitor.println(F("トルク OFF")); break;
    case 'q': cmdRun(16.0f, 3); break;
    case 'r': cmdRun(48.0f, 3); break;
    case 'b': cmdRun(-16.0f, 3); break;
    case 's': stopServo(); Monitor.println(F("停止指令を送りました")); break;
    case 'h': printHelp(); break;
    case '\n': case '\r': case ' ': break;
    default: break;
  }
}
