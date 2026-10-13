# flycar_q

Uno Q に載せる本番のアプリ。最新のフレームから左右の赤と青の占有を作り、`Plant.steps` で 20 ms 分の膜を進めて、左右のタイヤを回す。

## 動かし方

ボード上の置き場所は `~/ArduinoApps/flycar_q`。アプリだけだと `flycar` を import できない。パッケージも同じ `python/` に置く。リポジトリ直下で次を実行する。

```bash
scp -r src/flycar_q arduino@<ホスト名>.local:~/ArduinoApps/
scp -r src/flycar arduino@<ホスト名>.local:~/ArduinoApps/flycar_q/python/
```

SSH で入って起動する。起動コマンドはシェルに戻る。

```bash
ssh arduino@<ホスト名>.local
arduino-app-cli app start ~/ArduinoApps/flycar_q/
```

止めるときは、同じ SSH セッションで次を実行する。

```bash
arduino-app-cli app stop ~/ArduinoApps/flycar_q/
```

`No Colon In First Item Of Depfile` と出たら、スケッチのキャッシュが壊れている。消してから起動し直す。

```bash
rm -rf ~/ArduinoApps/flycar_q/.cache
arduino-app-cli app start ~/ArduinoApps/flycar_q/
```

ログは次で見る。1 秒に 1 行、左右の赤、左右の青、右と左のパルス、モードが出る。

```bash
arduino-app-cli app logs ~/ArduinoApps/flycar_q/ --tail 50
```

Python だけ直したときは、スケッチのキャッシュは消さなくてよい。止めてからコピーし、起動し直す。`src/flycar` を直したときも、上の 2 本目の `scp` をやり直す。

カメラのつなぎ方は [camera_capture_q](../../research/camera_capture_q/README.md) と同じ。USB-C を PC に刺したデバイスモードではカメラは列挙されない。給電できるハブの先に Brio 100 を置く。

## 周期

フレームを取るループと、膜のループは分けてある。暗い部屋ではシャッターが 250 ms まで伸び、読み出しを 20 ms の中で待つと膜が止まる。

| 周期 | 処理 |
| --- | --- |
| カメラの間隔 | 最新の 1 枚を覚えておく。4 fps なら同じ絵を繰り返し、30 fps なら間引く |
| 0.10 秒 | その絵から左右の赤と青を作り直す |
| 0.02 秒 | `Plant.steps` を 1 回呼び、パルスをスケッチへ送る |

起動直後の 20 フレームは指令を出さない。露出が上がる前の絵はほぼ黒い。

スケッチは 0.45 秒パルスが来ないと止める。Python が落ちたときも車輪は止まる。

## まだ床で合わせる数

色の範囲は `src/flycar/occupancy.py` の HSV で、2026-10-12 の見本に合わせてある。OpenCV の色相は 0〜179。赤は 0〜14 と 170〜179、彩度 95 以上、明度 245 以上。この部屋の赤いスマホはそこまで明るい。肌は同じ色相でも明度が約 214 で届かず、本棚の赤い背表紙は暗いので数えない。青は 88〜106、彩度 80 以上、明度 180 以上。スマホの水色は色相 90 前後、本棚の青は 111 前後なので、本棚では回らない。純青（色相 120）も対象の外である。半画面の 4% に届かない遠い画面は空のまま。紙やテープはまだ見ていない。画面いっぱいの赤は、明度 245 だと片側が 0.75 に届かないことがあり、両側が埋まったときの停止はまだこの見本では起きない。

速度の倍率は `src/flycar/pulse.py`。正面の赤が落ち着く 0.20 m/s を、ラジコンで気持ちよく走ったパルス 160 に対応させている。サーボが動き出す下限より小さい指令は、計算上は回っていても車は動かない。

画面の左が車の右になる取り付けなら、`python/config.py` の `MIRROR` を `True` にする。

## ファイル

| 場所 | 内容 |
| --- | --- |
| `python/main.py` | 0.10 秒と 0.02 秒のループ |
| `python/camera.py` | Brio を開き、最新フレームを置く |
| `python/motors.py` | `setMotorSpeed` をスケッチへ送る |
| `python/config.py` | 左右反転と、上の二つの周期 |
| `python/bootstrap.py` | `flycar` の import 先を足す |
| `sketch/sketch.ino` | Bridge の登録と `loop` |
| `sketch/motors.cpp` | ピン、パルス、無受信停止 |
| `src/flycar` | 占有、膜、m/s からパルス |

## 車輪

右がピン D3、左がピン D5。指令 -255〜255 を 1000〜2000 µs にする。1500 µs が停止。左は反時計回りが前進、右は時計回りが前進。`setMotorSpeed` の引数は右、左の順。正のヨーは左旋回なので、そのとき左のパルスが右より小さい。

このシャーシは時計回りが速い。`sketch/motors.cpp` の `CCW_GAIN` は 1.62 で、反時計回り側だけパルスの幅を広げる。ラジコンの前進、速度 40 のときの値である。速度 67 では 1.17 のほうがよかった。速度で変わるので、今は一つの式にはしていない。`research/motor_test` のスケッチも同じ定数である。
