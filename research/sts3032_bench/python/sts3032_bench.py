# STS3032 ベンチ測定スクリプト — PC + FE-URT2 用
# 作成: 2026-11-21。sts3032-bench-plan.md の項目 1–5 を回すためのもの。
# 前提: ID 分けとモード 1（速度閉ループ）設定は FD / feetech-cli で済ませてあること。
#       回転テストには外部 6 V 電源が要る。USB 給電のまま回さないこと。
#
# 使い方（サーボ到着後、ベンチ PC で）:
#   pip install feetech-servo-sdk
#   python sts3032_bench.py --self-test            # ハード無しで換算だけ確認
#   python sts3032_bench.py --port COM5 --check    # ping + モード/電圧の読みだけ
#   python sts3032_bench.py --port COM5 --rpm 48 --seconds 5        # 項目 1
#   python sts3032_bench.py --port COM5 --rpm 16 --seconds 5        # 項目 2
#   python sts3032_bench.py --port COM5 --rpm -48 --seconds 5       # 項目 4（後進）
#   python sts3032_bench.py --port COM5 --stop     # 両輪を止めるだけ
# Linux/macOS のポート例: /dev/ttyUSB0, /dev/tty.usbserial-XXXX
#
# 速度の単位は steps/s（1 単位 = 1 step/s、4096 steps/回転）。
# 48 RPM = 3277、16 RPM = 1092。後進は sign-magnitude で bit 15 を立てる
# （-48 RPM = 36045）。旧メモの「48 RPM ≈ 66」は誤りで、使わないこと。
# 根拠は sts3032-python-bench-note.md の 2026-11-21 16:10 JST 追記。
# レジスタは STS 系の共通マップ（Waveshare 版 SMS_STS.h で確認済み）。
# 2026-11-22 に myCobot 実測・STS3032 製品ページ・feetech-cli の制御表でも
# 照合済み（詳細は sts3032-python-bench-note.md の追記）。STS3032 付属
# マニュアル / FD 表示 / `feetech info 1 --all` で到着時に最終確認すること。
#   GOAL_SPEED 46–47, PRESENT_SPEED 58–59, TORQUE_ENABLE 40, MODE 33
# Present Speed の読みは 50 steps/s 刻み（48 RPM で ±0.8%、16 RPM で ±2.3%）。

import argparse
import sys
import time

# レジスタ（STS 系共通マップ。4 つの独立した実装・実測で照合済み。
#  STS3032 実機での最終確認は到着時に）
ADDR_GOAL_SPEED = 46
ADDR_PRESENT_SPEED = 58
ADDR_TORQUE_ENABLE = 40
ADDR_MODE = 33
ADDR_PRESENT_VOLTAGE = 62
ADDR_PRESENT_TEMPERATURE = 63
ADDR_PRESENT_LOAD = 60  # 2 バイト。STS3032 は電流フィードバックが無く
# （Switch Science の仕様欄: 位置・温度・速度・電圧・負荷）、addr 69 は常に 0 を
# 返した（2026-11-28 実測）。負荷は bit 10 が符号、0–1000 が 0.1% 単位。
STEPS_PER_REV = 4096
BAUDRATE = 1_000_000

DEFAULT_IDS = (1, 2)  # 右=1、左=2（bench-plan §2 の例）


def rpm_to_steps(rpm):
    """RPM -> steps/s（符号なしの大きさ）。48 RPM -> 3277、16 RPM -> 1092。"""
    return round(abs(rpm) / 60.0 * STEPS_PER_REV)


def rpm_to_goal_value(rpm):
    """RPM -> GOAL_SPEED に書く値。後進は sign-magnitude（bit 15 を立てる）。"""
    steps = rpm_to_steps(rpm)
    return (0x8000 | steps) if rpm < 0 else steps


def goal_value_to_rpm(value):
    """GOAL_SPEED / PRESENT_SPEED の生値 -> RPM（sign-magnitude と解釈）。"""
    steps = value & 0x7FFF
    rpm = steps / STEPS_PER_REV * 60.0
    return -rpm if value & 0x8000 else rpm


def to_bytes_2(value):
    return [value & 0xFF, (value >> 8) & 0xFF]


def self_test():
    cases = [(48, 3277), (16, 1092), (-48, 36045), (-16, 33860), (0, 0)]
    ok = True
    for rpm, want in cases:
        got = rpm_to_goal_value(rpm)
        mark = "OK " if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"{mark} {rpm:+d} RPM -> {got} (期待 {want})")
    # 往復チェック
    for rpm in (48, 16, -48):
        back = goal_value_to_rpm(rpm_to_goal_value(rpm))
        print(f"    往復 {rpm:+d} RPM -> {back:+.2f} RPM")
    print("self-test:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


class Bench:
    def __init__(self, port, ids):
        import scservo_sdk as scs  # pip install feetech-servo-sdk

        self.scs = scs
        self.port_handler = scs.PortHandler(port)
        self.packet_handler = scs.PacketHandler(0)
        # 同じ ID の重複は落とす（--ids 1 1 のような 1 個運用で
        # GroupSyncWrite.addParam が重複 ID で失敗するため。2026-11-28 実測）
        self.ids = list(dict.fromkeys(ids))

    def __enter__(self):
        if not self.port_handler.openPort():
            raise SystemExit("ポートが開けませんでした。URT2 が挿さっているか、"
                             "ポート名（COMx / /dev/ttyUSB0）を確認してください。")
        self.port_handler.setBaudRate(BAUDRATE)
        return self

    def __exit__(self, *exc):
        try:
            self.stop()
        finally:
            self.port_handler.closePort()
        return False

    def ping(self, scs_id):
        _model, result, _err = self.packet_handler.ping(
            self.port_handler, scs_id)
        return result == self.scs.COMM_SUCCESS

    def read1(self, scs_id, address):
        value, result, _err = self.packet_handler.read1ByteTxRx(
            self.port_handler, scs_id, address)
        if result != self.scs.COMM_SUCCESS:
            raise RuntimeError(f"ID {scs_id} の読み取りに失敗しました "
                               f"(address {address})")
        return value

    def read2(self, scs_id, address):
        value, result, _err = self.packet_handler.read2ByteTxRx(
            self.port_handler, scs_id, address)
        if result != self.scs.COMM_SUCCESS:
            raise RuntimeError(f"ID {scs_id} の読み取りに失敗しました "
                               f"(address {address})")
        return value

    def write1(self, scs_id, address, value):
        # write1ByteTxRx -> writeTxRx は (result, error) の 2 値を返す
        result, _err = self.packet_handler.write1ByteTxRx(
            self.port_handler, scs_id, address, value)
        if result != self.scs.COMM_SUCCESS:
            raise RuntimeError(f"ID {scs_id} の書き込みに失敗しました "
                               f"(address {address})")

    def torque_on(self):
        for scs_id in self.ids:
            self.write1(scs_id, ADDR_TORQUE_ENABLE, 1)

    def set_speed_all(self, rpm):
        """両輪へ同じ速度を SyncWrite。feetech-servo-sdk には WriteSpe が無いので
        汎用層（GroupSyncWrite）で GOAL_SPEED 46–47 に書く。"""
        value = rpm_to_goal_value(rpm)
        sync = self.scs.GroupSyncWrite(
            self.port_handler, self.packet_handler,
            ADDR_GOAL_SPEED, 2)
        for scs_id in self.ids:
            if not sync.addParam(scs_id, to_bytes_2(value)):
                raise RuntimeError(f"ID {scs_id} の addParam に失敗しました")
        if sync.txPacket() != self.scs.COMM_SUCCESS:
            raise RuntimeError("SyncWrite の送信に失敗しました")
        return value

    def read_speeds(self):
        """両輪の Present Speed（58–59）を SyncRead で読む。"""
        sync = self.scs.GroupSyncRead(
            self.port_handler, self.packet_handler,
            ADDR_PRESENT_SPEED, 2)
        for scs_id in self.ids:
            sync.addParam(scs_id)
        if sync.txRxPacket() != self.scs.COMM_SUCCESS:
            raise RuntimeError("SyncRead に失敗しました")
        out = {}
        for scs_id in self.ids:
            if not sync.isAvailable(scs_id, ADDR_PRESENT_SPEED, 2):
                raise RuntimeError(f"ID {scs_id} の速度が読めませんでした")
            raw = sync.getData(scs_id, ADDR_PRESENT_SPEED, 2)
            out[scs_id] = goal_value_to_rpm(raw)
        return out

    def read_loads(self):
        """各 ID の Present Load（60–61）を % で読む。項目 3 の負荷判定用。
        STS の負荷は bit 10 が符号、絶対値 0–1000 が 0.1% 単位。"""
        out = {}
        for scs_id in self.ids:
            raw = self.read2(scs_id, ADDR_PRESENT_LOAD)
            pct = (raw & 0x3FF) / 10.0
            out[scs_id] = -pct if raw & 0x0400 else pct
        return out

    def stop(self):
        try:
            self.set_speed_all(0)
        except Exception:
            pass  # 終了時の停止は失敗しても握りつぶす（ポートを閉じるため）


def main(argv=None):
    ap = argparse.ArgumentParser(description="STS3032 ベンチ測定（項目 1/2/4）")
    ap.add_argument("--port", default=None,
                    help="URT2 のポート (例: COM5, /dev/ttyUSB0)")
    ap.add_argument("--ids", type=int, nargs=2, default=list(DEFAULT_IDS),
                    help="左右の ID（既定: 1 2）")
    ap.add_argument("--rpm", type=float, default=48.0,
                    help="指令 RPM（既定: 48。後進は負値）")
    ap.add_argument("--seconds", type=float, default=5.0,
                    help="回す秒数（既定: 5）")
    ap.add_argument("--check", action="store_true",
                    help="回さず ping + モード/電圧の読みだけ")
    ap.add_argument("--stop", action="store_true", help="両輪を止めるだけ")
    ap.add_argument("--self-test", action="store_true",
                    help="ハード無しで RPM <-> 指令値の換算だけ確認")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.port:
        ap.error("--port が必要です（--self-test を除く）")

    print("注意: 回転テストには外部 6 V 電源が必要です。USB 給電だけでは回さないでください。")
    with Bench(args.port, args.ids) as bench:
        for scs_id in args.ids:
            if not bench.ping(scs_id):
                raise SystemExit(f"ID {scs_id} に応答がありません。"
                                 "1 個ずつ接続して ID を確認してください。")
            print(f"ID {scs_id}: ping OK")
        if args.check:
            for scs_id in args.ids:
                # MODE 33 と電圧 62・温度 63 はいずれも 1 バイト。
                # 62 を read2 すると電圧＋温度<<8 の合成値になるので read1 で読む。
                mode = bench.read1(scs_id, ADDR_MODE)
                volt_raw = bench.read1(scs_id, ADDR_PRESENT_VOLTAGE)
                temp_raw = bench.read1(scs_id, ADDR_PRESENT_TEMPERATURE)
                print(f"ID {scs_id}: MODE={mode}（1=速度閉ループのはず） "
                      f"電圧={volt_raw / 10:.1f} V 温度={temp_raw} ℃")
            print("check 終了（回していません）")
            return 0
        if args.stop:
            print("両輪を停止しました")
            return 0

        bench.torque_on()
        goal = bench.set_speed_all(args.rpm)
        print(f"指令: {args.rpm:+.0f} RPM -> GOAL_SPEED={goal} "
              f"(ID {args.ids}) を {args.seconds:.0f} 秒回します")
        samples = {scs_id: [] for scs_id in args.ids}
        t_end = time.time() + args.seconds
        try:
            while time.time() < t_end:
                speeds = bench.read_speeds()
                try:
                    loads = bench.read_loads()
                except Exception:
                    loads = {}
                for scs_id, rpm in speeds.items():
                    samples[scs_id].append(rpm)
                print("  " + "  ".join(
                    f"ID {i}: {speeds[i]:+6.1f} RPM / 負荷 {loads.get(i, float('nan')):5.1f} %"
                    for i in args.ids))
                time.sleep(0.5)
        finally:
            bench.stop()
        print("停止しました")
        for scs_id in args.ids:
            vals = samples[scs_id]
            mean = sum(vals) / len(vals) if vals else 0.0
            print(f"ID {scs_id}: 平均 {mean:+.1f} RPM "
                  f"(指令 {args.rpm:+.0f} RPM、読み {len(vals)} 回)")
        if len(args.ids) == 2:
            m = [sum(samples[i]) / len(samples[i]) for i in args.ids]
            diff = abs(m[0] - m[1])
            base = max(abs(m[0]), abs(m[1]), 1e-9)
            print(f"左右差: {diff:.1f} RPM（{diff / base * 100:.1f}%）"
                  " — 項目 1 の合格は「数%以内」")
        print("項目 3（負荷耐性）はこのスクリプトを --rpm 48 で回しながら、"
              "軸に指で軽く負荷をかけて上の読みが指令に戻るかを見てください。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
