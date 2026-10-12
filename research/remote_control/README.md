# ラジコン

Arduino Uno Q の App Lab アプリ。ブラウザに Brio 100 の映像を出し、十字キーで左右の車輪を動かす。車輪のピンとパルスは [motor_test](../motor_test/) で前進と後進を確認したときのまま。

## 動かし方

ボード上の置き場所は `~/ArduinoApps/remote_control`。PC のリポジトリから置くときは、リポジトリ直下で次を実行する。

```bash
scp -r research/remote_control arduino@<ホスト名>.local:~/ArduinoApps/
```

SSH で入って起動する。起動コマンドはシェルに戻る。アプリはそのまま動いている。

```bash
ssh arduino@<ホスト名>.local
arduino-app-cli app start ~/ArduinoApps/remote_control/
```

止めるときは、同じ SSH セッションで次を実行する。

```bash
arduino-app-cli app stop ~/ArduinoApps/remote_control/
```

`No Colon In First Item Of Depfile` と出たら、スケッチのキャッシュが壊れている。消してから起動し直す。

```bash
rm -rf ~/ArduinoApps/remote_control/.cache
arduino-app-cli app start ~/ArduinoApps/remote_control/
```

ページはポート 7000。同じ LAN のブラウザで `http://<ホスト名>.local:7000` を開く。

App Lab でこのディレクトリを開いて Run してもよい。

カメラのつなぎ方は [camera_capture_q](../camera_capture_q/README.md) と同じ。USB-C を PC に刺したデバイスモードではカメラは列挙されない。給電できるハブの先に Brio 100 を置く。

## 操作

| 入力 | 車輪 |
| --- | --- |
| ↑ または W | 前進 |
| ↓ または S | 後退 |
| ← または A | その場で左旋回 |
| → または D | その場で右旋回 |
| 前進と左右を同時 | 曲がる側の車輪を止め、反対側だけ進める |
| キーを離す、スペース、画面の「停止」 | 停止 |

画面の十字も同じ。速度スライダの既定は 160。`motor_test` で回した 255 まで上げられる。正が前進で、表示の右と左は `setMotorSpeed` に渡す値。

反時計回りの倍率スライダは 1.00〜2.00。初期値は 1.62 で、前進・速度 40 のときのもの。速度 67 では 1.17 のほうがよかった。速度で変わるので、今は一つの式にはしていない。押したまま変えると、その指令のままパルス幅が変わる。ページを開き直しても、そのブラウザのタブには最後の値が残る。

キーを押しているあいだ、ページは 0.2 秒ごとに同じ指令を送り直す。ボードは 0.45 秒受信が無いと止める。ページを閉じたとき、別の窓へ移ったときも止める。ブラウザは 1 つにする。

## カメラ

プレビューは 1280×720 の MJPG。`capture.py` で映ったサイズと同じ。640×480 は露出が上がる前に撮るとほぼ黒だった。

`Camera` は fps に 0 を受け付けない。開くときに `STREAM_FPS`（10）をカメラへ書くと、シャッターはその間隔で頭打ちになる。開いた直後に `capture.py` と同じ 3 つをセットする。`auto_exposure=3`、`exposure_dynamic_framerate=1`、`white_balance_automatic=1`。シャッターは部屋の明るさに合わせて最長 250 ms まで伸び、fps はそれに追従して下がる。ページへ出す前に 20 フレーム待ち、ガンマ 0.8 で影を持ち上げる。ガンマだけでは真っ黒は絵にならない。

起動ログの `camera:` 行に、デバイスと 20 フレーム後の平均輝度が出る。

```bash
arduino-app-cli app logs ~/ArduinoApps/remote_control/ --tail 50
```

Python だけ直したときは、スケッチのキャッシュは消さなくてよい。止めてからコピーし、起動し直す。

## 車輪

右がピン D3、左がピン D5。指令 -255〜255 を 1000〜2000 µs にする。1500 µs が停止。左は CCW が前進、右は CW が前進。`setMotorSpeed` の引数は右、左の順。右旋回はその場で右が負、左が正。前進しながらなら、曲がる側の車輪が止まり、反対側だけ進む。

このシャーシは時計回りが速い。ページの倍率が、反時計回り側だけ 1500 µs からの幅を広げる。初期値は 1.62（`CCW_GAIN_MILLI` は 1620）で、前進・速度 40 のときのもの。速度 67 では 1.17 のほうがよかった。`research/motor_test` と `src/flycar_q/sketch/motors.cpp` の `CCW_GAIN` も、いったん 1.62 のままにしてある。
