# flycar_q

Uno Q に載せる本番のアプリ。カメラの 1 フレームを左右の赤と青にし、`src/flycar` の車輪則を通して、左右のタイヤを回す。`research/` のラジコンやモーター試験とは別に置く。

一周はまだつながっていない。このディレクトリをボードで起動しても、車輪は回らない。

## 中身

| 場所 | 内容 |
|---|---|
| `python/main.py` | メイン処理。カメラ、`Plant`、マイコンはまだ呼ばない |
| `sketch/sketch.ino` | マイコン側。パルスを出す処理はまだ無い |
| `src/flycar` | 車輪則と画角。import 名は `flycar` |

ピンとパルスは [remote_control](../../research/remote_control/README.md) で確認してある。右が D3、左が D5。指令 -255〜255 を 1000〜2000 µs にし、1500 µs が停止。左は反時計回りが前進、右は時計回りが前進。

ボードへ置くときは、リポジトリ直下で次を実行する。置き場所は `~/ArduinoApps/flycar_q`。

```bash
scp -r src/flycar_q arduino@<ホスト名>.local:~/ArduinoApps/
```

今の中身はそこで起動してもすぐ終わる。
