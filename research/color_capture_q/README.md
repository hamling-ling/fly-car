# 色の矩形

Arduino Uno Q の App Lab アプリ。ブラウザに Brio 100 の映像を出し、絵を止めて赤と青を4点で囲んで保存する。車輪は動かさない。スケッチは無い。

保存先は `samples/marked/`。1 枚につき JPEG と、同じ名前の `.json` がある。囲いの中の色は、あとでゲインとシャッターから推定する。前のボタン別フォルダ（`background/` など）はそのまま残してある。ここには足さない。

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

対象を出してから 1 秒ほど待ち、露出が落ち着いてから「絵を止める」。止めた絵の上で「赤の4点」か「青の4点」を選び、輪郭を順に4点たたく。斜めに写った紙も囲える。点は打った順につながる。交差する4点と、面積が 8×8 画素より小さい囲いは捨てる。赤と青は同じ絵に両方置ける。片方だけでも保存できる。

「この4点で保存」で、止めた JPEG とその4点を書く。ライブの次のフレームは保存しない。やり直すときは「直前の点を消す」か、色ごとに消して打ち直すか、「ライブに戻る」。

赤も青も映っていない絵は、点を置かずに「赤も青も写っていない」を押す。JSON の `neither` が true になり、`red` と `blue` は null である。点が残っているとそのボタンは押せない。

メモ欄は距離や照明。空でも保存できる。80 文字までで、ファイル名には入らず `.json` に入る。

「保存した絵を見る」で、保存済みの絵を古い順に4点つきで見る。左右のキーかスライダで送る。囲いが 1 つの枚は「赤にする」「青にする」で付け替えられる。「この枚を消す」はその JPEG と JSON を消す。軸に沿った古い矩形も、四隅の4点として見える。

## 保存されるもの

プレビューも保存も 1280×720 の MJPG から取った BGR のまま。ガンマは掛けない。プレビューの JPEG 品質は 60、止めた絵と保存は 95。保存ファイルは、画面に出している静止画そのもの。

`Camera` は fps に 0 を受け付けない。開くときに `STREAM_FPS`（10）をカメラへ書くと、シャッターはその間隔で頭打ちになる。開いた直後に `capture.py` と同じ 3 つをセットする。`auto_exposure=3`、`exposure_dynamic_framerate=1`、`white_balance_automatic=1`。この自動露出は残す。切るとゲインとシャッターが条件として動かず、夕方の部屋はほぼ黒になる。記録するのは、絵を止めた瞬間の値。

点は画像の左上を原点にした画素で、打った順に4つ入る。`x` と `y` と `width` と `height` は、その4点を含む軸に沿った外接矩形で、両端の画素を含む。囲いの本体は `points` である。描いていない色は `null`。2026-10-13 までの保存は `points` が無く、軸に沿った矩形だけである。

```json
{
  "file": "samples/marked/20261013T120000_000.jpg",
  "width": 1280,
  "height": 720,
  "exposure_time_absolute": 666,
  "gain": 215,
  "red": {
    "points": [[40, 80], [240, 90], [230, 440], [30, 420]],
    "x": 30,
    "y": 80,
    "width": 211,
    "height": 361
  },
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

## しきい値

PC に `samples/marked/` を置いてから、リポジトリ直下で次を実行する。赤と青の4点から下限を計算し、`src/flycar/color_thresholds.json` を書き換える。`occupancy.py` は起動時にこのファイルを読む。

```bash
python3 research/color_capture_q/fit_thresholds.py
```

囲いの画素の 80% 以上が残る範囲で、彩度を先に、明度を次に、10 刻みで上げる。色相は、赤が 0 度をまたぐので 2 度刻みで端を広げ、青は 10 度刻みで切る。赤でも青でもない絵はこの計算に入れない。半画面が 4% 以上になったものだけを最後に出す。ファイルを替えたら、車のアプリを起動し直す。ボードへは `src/flycar` ごとコピーする。
