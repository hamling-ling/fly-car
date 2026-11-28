# STS3032 の ID 変更 + モード 1 設定 — 2 台目専用、PC + FE-URT2 用
# 作成: 2026-11-28。工場出荷時は全個体 ID=1 なので、2 台目を単独でつないで
# ID=2 に変え、ついでに速度閉ループ（モード 1）まで設定する。
# 1 台目をバスに残したまま実行すると ID が衝突するので、必ず 2 台目だけで。
#
# 使い方:
#   python sts3032_set_id.py --port /dev/ttyACM1                 # ID 1 -> 2 + モード 1
#   python sts3032_set_id.py --port /dev/ttyACM1 --from-id 1 --new-id 2
# 回転はしない。

import argparse
import sys
import time

ADDR_ID = 5              # EEPROM
ADDR_MODE = 33           # EEPROM。1 = 速度閉ループ
ADDR_TORQUE_ENABLE = 40
ADDR_LOCK = 55           # EEPROM ロック（0=解除, 1=ロック）
ADDR_PRESENT_VOLTAGE = 62
BAUDRATE = 1_000_000


def main():
    ap = argparse.ArgumentParser(description="STS3032 の ID 変更とモード 1 設定")
    ap.add_argument("--port", required=True, help="URT2 のポート (例: /dev/ttyACM1)")
    ap.add_argument("--from-id", type=int, default=1, help="現在の ID（既定: 1）")
    ap.add_argument("--new-id", type=int, default=2, help="新しい ID（既定: 2）")
    args = ap.parse_args()

    import scservo_sdk as scs

    port = scs.PortHandler(args.port)
    if not port.openPort():
        print("ポートが開けませんでした。ポート名と権限を確認してください。")
        return 1
    port.setBaudRate(BAUDRATE)
    pkt = scs.PacketHandler(0)

    def write1(sid, addr, value, label):
        result, err = pkt.write1ByteTxRx(port, sid, addr, value)
        print(f"  write {label} (ID {sid}, addr {addr} = {value}): "
              f"result={result}, サーボエラーバイト = {err}")
        time.sleep(0.05)
        return result == scs.COMM_SUCCESS

    def read1(sid, addr):
        value, result, _err = pkt.read1ByteTxRx(port, sid, addr)
        if result != scs.COMM_SUCCESS:
            raise RuntimeError(f"読み取り失敗 (ID {sid}, address {addr})")
        return value

    def ping(sid):
        _m, result, _e = pkt.ping(port, sid)
        return result == scs.COMM_SUCCESS

    try:
        old, new = args.from_id, args.new_id
        if not ping(old):
            print(f"ID {old} に応答がありません。2 台目だけが接続されているか"
                  "確認してください。")
            return 1
        print(f"ID {old}: ping OK, 電圧 = {read1(old, ADDR_PRESENT_VOLTAGE) / 10:.1f} V")
        if ping(new) and new != old:
            print(f"注意: ID {new} にも応答があります。別のサーボがバスに残って"
                  "いませんか。中止します。")
            return 1
        # EEPROM 書き込み: トルク OFF -> ロック解除 -> ID 変更
        write1(old, ADDR_TORQUE_ENABLE, 0, "TORQUE_ENABLE")
        write1(old, ADDR_LOCK, 0, "LOCK 解除")
        write1(old, ADDR_ID, new, "ID")
        time.sleep(0.1)
        if not ping(new):
            print(f"ID {new} で ping が返りません。電源を入れ直してから "
                  f"sts3032_bench.py --check --ids {new} {new} で確認してください"
                  "（EEPROM 書き込みは応答なしでも通っていることがあります）。")
            return 1
        print(f"ID {new}: ping OK（ID 変更が反映されました）")
        # 新 ID でモード 1 を設定してロックを戻す
        write1(new, ADDR_TORQUE_ENABLE, 0, "TORQUE_ENABLE")
        write1(new, ADDR_MODE, 1, "MODE")
        write1(new, ADDR_LOCK, 1, "LOCK")
        mode = read1(new, ADDR_MODE)
        volt = read1(new, ADDR_PRESENT_VOLTAGE) / 10.0
        print(f"ID {new}: MODE = {mode}, 電圧 = {volt:.1f} V")
        if mode != 1:
            print("注意: MODE が 1 になっていません。電源を入れ直して読み直して"
                  "ください。")
            return 1
        print("2 台目の準備完了（ID=2、速度閉ループ）。トルクは OFF のままです。")
        return 0
    finally:
        port.closePort()


if __name__ == "__main__":
    sys.exit(main())
