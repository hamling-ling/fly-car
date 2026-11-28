# STS3032 を速度閉ループ（モード 1）に設定する小さなスクリプト — PC + FE-URT2 用
# 作成: 2026-11-28。工場出荷時は MODE=0（位置モード）なので、回転テストの前に
# これでモード 1 にして読み戻す。sts3032_bench.py と同じレジスタマップ。
#
# v2 (2026-11-28): 初版は MODE(33) への書き込みで COMM 失敗になった。
# 失敗の内訳（結果コードとサーボのエラーバイト）を全部印字する診断版にした。
# EEPROM 書き込みは応答が返らない／遅れる個体があるので、成否は最終的に
# 「電源を入れ直して MODE を読み戻す」ことで判定する。
#
# 使い方:
#   pip install feetech-servo-sdk
#   python sts3032_set_mode.py --port /dev/ttyACM1          # ID 1 をモード 1 に
#   python sts3032_set_mode.py --port /dev/ttyACM1 --id 2   # ID 指定
# 回転はしない（トルク OFF のまま終わる）。

import argparse
import sys
import time

ADDR_MODE = 33           # EEPROM。1 = 速度閉ループ
ADDR_TORQUE_ENABLE = 40
ADDR_LOCK = 55           # EEPROM ロック（0=解除, 1=ロック）
ADDR_PRESENT_VOLTAGE = 62
BAUDRATE = 1_000_000


def main():
    ap = argparse.ArgumentParser(description="STS3032 モード 1（速度閉ループ）設定")
    ap.add_argument("--port", required=True, help="URT2 のポート (例: /dev/ttyACM1)")
    ap.add_argument("--id", type=int, default=1, help="サーボ ID（既定: 1）")
    args = ap.parse_args()

    import scservo_sdk as scs

    port = scs.PortHandler(args.port)
    if not port.openPort():
        print("ポートが開けませんでした。ポート名と権限を確認してください。")
        return 1
    port.setBaudRate(BAUDRATE)
    pkt = scs.PacketHandler(0)
    sid = args.id

    def describe(result):
        names = {
            scs.COMM_SUCCESS: "COMM_SUCCESS",
            scs.COMM_PORT_BUSY: "COMM_PORT_BUSY",
            scs.COMM_TX_FAIL: "COMM_TX_FAIL",
            scs.COMM_RX_FAIL: "COMM_RX_FAIL",
            scs.COMM_TX_ERROR: "COMM_TX_ERROR",
            scs.COMM_RX_WAITING: "COMM_RX_WAITING",
            scs.COMM_RX_TIMEOUT: "COMM_RX_TIMEOUT（応答なし）",
            scs.COMM_RX_CORRUPT: "COMM_RX_CORRUPT（応答破損）",
            scs.COMM_NOT_AVAILABLE: "COMM_NOT_AVAILABLE",
        }
        return names.get(result, f"result={result}")

    def write1(addr, value, label):
        result, err = pkt.write1ByteTxRx(port, sid, addr, value)
        print(f"  write {label} (addr {addr} = {value}): {describe(result)}, "
              f"サーボエラーバイト = {err}")
        time.sleep(0.05)  # EEPROM 書き込みの完了待ち
        return result == scs.COMM_SUCCESS

    def read1(addr):
        value, result, err = pkt.read1ByteTxRx(port, sid, addr)
        if result != scs.COMM_SUCCESS:
            raise RuntimeError(f"読み取り失敗 (address {addr}): {describe(result)}")
        return value

    try:
        _model, result, _err = pkt.ping(port, sid)
        if result != scs.COMM_SUCCESS:
            print(f"ID {sid} に応答がありません。")
            return 1
        volt = read1(ADDR_PRESENT_VOLTAGE) / 10.0
        print(f"ID {sid}: ping OK, 現在の MODE = {read1(ADDR_MODE)}, 電圧 = {volt:.1f} V")
        if volt < 5.0:
            print("注意: 電圧が低いです。6 V が V1 端子に入っているか先に確認してください。"
                  "低電圧だと EEPROM 書き込みが保護で弾かれることがあります。")
        # EEPROM 書き込み: トルク OFF -> ロック解除 -> MODE=1 -> ロック
        write1(ADDR_TORQUE_ENABLE, 0, "TORQUE_ENABLE")
        write1(ADDR_LOCK, 0, "LOCK 解除")
        write1(ADDR_MODE, 1, "MODE")
        write1(ADDR_LOCK, 1, "LOCK")
        try:
            mode = read1(ADDR_MODE)
            print(f"ID {sid}: 設定後の MODE 読み戻し = {mode}")
            if mode == 1:
                print("速度閉ループ（モード 1）になっています。トルクは OFF のままです。")
                return 0
        except RuntimeError as e:
            print(f"読み戻し失敗: {e}")
        print("この場では確定できませんでした。サーボの電源を入れ直してから "
              "sts3032_bench.py --check で MODE を読み直してください"
              "（書き込み自体は通っていて応答だけ返らない場合があります）。")
        return 1
    finally:
        port.closePort()


if __name__ == "__main__":
    sys.exit(main())
