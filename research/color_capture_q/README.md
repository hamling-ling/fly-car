# 色の矩形

Arduino Uno Q の App Lab アプリ。ブラウザに Brio 100 の映像を出し、絵を止めて赤と青の矩形を描いて保存する。車輪は動かさない。スケッチは無い。

保存先は `samples/marked/`。1 枚につき JPEG と、同じ名前の `.json` がある。矩形の中の色は、あとでゲインとシャッターから推定する。前のボタン別フォルダ（`background/` など）はそのまま残してある。ここには足さない。

## 動かし方

`flycar_q` と `remote_control` は止めてから起動する。カメラは一つしか開けない。

ボード上の置き場所は `~/ArduinoApps/color_capture_q`。PC のリポジトリから置くときは、リポジトリ直下で次を実行する。

```bash
scp -r research/color_capture_q arduino@<ホスト名>.local:~/ArduinoApps/
```

SSH で入って起動する。起動コマンドはシェルに戻る。アプリはそのまま動いている。

```bash
ssh arduino@<ホスト名>.local
arduino-app-cli app start ~/ArduinoApps/color_capture_q/
```

止めるときは、同じ SSH セッションで次を実行する。

```bash
arduino-app-cli app stop ~/ArduinoApps/color_capture_q/
```

ページはポート 7000。同じ LAN のブラウザで `http://<ホスト名>.local:7000` を開く。ラジコンと同じポートなので、同時には開かない。

App Lab でこのディレクトリを開いて Run してもよい。

カメラのつなぎ方は [camera_capture_q](../camera_capture_q/README.md) と同じ。USB-C を PC に刺したデバイスモードではカメラは列挙されない。給電できるハブの先に Brio 100 を置く。

## 撮り方

対象を出してから 1 秒ほど待ち、露出が落ち着いてから「絵を止める」。止めた絵の上で「赤の矩形」か「青の矩形」を選び、ドラッグする。赤と青は同じ絵に両方描ける。片方だけでも保存できる。8 画素より小さいドラッグは捨てる。

「この矩形で保存」で、止めた JPEG とその矩形を書く。ライブの次のフレームは保存しない。やり直すときは消して描き直すか、「ライブに戻る」。

赤も青も映っていない絵は、矩形を描かずに「赤も青も写っていない」を押す。JSON の `neither` が true になり、`red` と `blue` は null である。矩形が残っているとそのボタンは押せない。

メモ欄は距離や照明。空でも保存できる。80 文字までで、ファイル名には入らず `.json` に入る。

「保存した絵を見る」で、保存済みの絵を古い順に矩形つきで見る。左右のキーかスライダで送る。矩形が 1 つの枚は「赤にする」「青にする」で付け替えられる。「この枚を消す」はその JPEG と JSON を消す。

## 保存されるもの

プレビューも保存も 1280×720 の MJPG から取った BGR のまま。ガンマは掛けない。プレビューの JPEG 品質は 60、止めた絵と保存は 95。保存ファイルは、画面に出している静止画そのもの。

`Camera` は fps に 0 を受け付けない。開くときに `STREAM_FPS`（10）をカメラへ書くと、シャッターはその間隔で頭打ちになる。開いた直後に `capture.py` と同じ 3 つをセットする。`auto_exposure=3`、`exposure_dynamic_framerate=1`、`white_balance_automatic=1`。この自動露出は残す。切るとゲインとシャッターが条件として動かず、夕方の部屋はほぼ黒になる。記録するのは、絵を止めた瞬間の値。

矩形は画像の左上を原点にした画素。`x` と `y` が左上、`width` と `height` が大きさ。描いていない色は `null`。

```json
{
  "file": "samples/marked/20261013T120000_000.jpg",
  "width": 1280,
  "height": 720,
  "exposure_time_absolute": 666,
  "gain": 215,
  "red": { "x": 40, "y": 80, "width": 200, "height": 360 },
  "blue": null
}
```

`exposure_time_absolute` の単位は 100 µs。平均輝度、メモ、保存時刻も同じファイルに入る。

撮った JPEG はリポジトリに入れない。ボードから持ってくるときは、PC で次のようにする。

```bash
scp -r arduino@<ホスト名>.local:~/ArduinoApps/color_capture_q/samples .
```

起動ログは次で見る。

```bash
arduino-app-cli app logs ~/ArduinoApps/color_capture_q/ --follow
```
