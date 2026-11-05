# コネクトームの切り出し

トップの説明は [README](../README.md)。ここは MaleCNS の表を取り、巨大線維の loom 回路と DNa02 の走性回路だけを残す手順である。

git には元表も切り出し結果も入っていない。ノートのうち `research/notebooks/gf_loom_sim.ipynb` と `research/notebooks/chemotaxis_sim.ipynb` は、下の切り出し結果を読む。車の車輪則 `src/flycar/behavior.py` と画角のノートは、この表が無くても動く。

## Release から取る

Release [data-2026-10-05](https://github.com/hamling-ling/fly-car/releases/tag/data-2026-10-05) に置いてある。元表は MaleCNS v1.0 のコピーで、ライセンスは CC BY 4.0 である。正本は https://male-cns.janelia.org/download にある。

リポジトリ直下で次を実行すると、`data/malecns/` に元表と切り出し結果が揃う。

```bash
rel=https://github.com/hamling-ling/fly-car/releases/download/data-2026-10-05
mkdir -p data/malecns
cd data/malecns

curl -L -C - -O "$rel/body-annotations-male-cns-v1.0-minconf-0.5.feather"
curl -L -C - -O "$rel/body-neurotransmitters-male-cns-v1.0.feather"
curl -L -C - -O "$rel/connectome-weights-male-cns-v1.0-minconf-0.5.feather"
curl -L -C - -O "$rel/gf_loom.json"
curl -L -C - -O "$rel/gf-loom.tar.gz"
curl -L -C - -O "$rel/steer-dna02.tar.gz"
curl -L -C - -O "$rel/SHA256SUMS"
sha256sum -c SHA256SUMS

tar -xzf gf-loom.tar.gz
tar -xzf steer-dna02.tar.gz
```

`gf-loom.tar.gz` は巨大線維の loom 回路、`steer-dna02.tar.gz` は DNa02 の走性回路である。ノートだけ回すなら、この 2 つを展開すればよい。結合表は約 1 GB ある。Release の tar には、シナプス座標の `syn-points` は入っていない。

## 正本から表を取る

画面の列対応には、上の Release には無い `syn-points` が要る。正本は https://male-cns.janelia.org/download/ で、ライセンスは CC BY 4.0 である。次は注釈、伝達物質、結合重み、シナプス座標の 4 つを `data/malecns/` に置く。電顕ボリューム、骨格、シナプス相手の表は取らない。サイズが同じファイルは取り直さない。短いファイルは続きから取る。`syn-points` は約 13 GB ある。

```bash
python3 scripts/download_malecns.py
```

サイズが同じファイルは取り直さない。走査が LZ4 の展開エラーで止まったときは、そのファイルを消してからもう一度実行する。4 つとも取り直すときは `--force` を付ける。

## 画面の列対応を作る

LC4 と LPLC2 の画面上の位置は、細胞体から推定しない。`syn-points` の各後シナプスには、小葉または小葉板の列番号 `a` と `b` が付いている。1 本の位置は、その細胞の後シナプスが載る列の平均である。

`a` が大きい側が眼の外側である。左端を左眼の `a` 最大、画面中央を両眼の `a` 最小、右端を右眼の `a` 最大にする。`b` が小さい側を上にする。範囲は、その細胞種が触れた列ではなく、その神経叢の全列である。左右の両方にラベルがある後シナプスは左に置く。LC4 は小葉、LPLC2 は小葉板を使う。ノートの帯ごとの上下の引き伸ばしは図のためで、この対応には入れない。

```bash
python3 scripts/build_camera_map.py
```

キャッシュが既にあるときはシナプス表を走査しない。作り直すときは `--rebuild` を付ける。走査は 1 回で、1 分少しかかる。

| ファイル | 内容 |
|---|---|
| `data/malecns/lc4-camera/lc4_lobula_posts.npz` | LC4 の小葉後シナプスと、小葉の全列の中心 |
| `data/malecns/lplc2-camera/lplc2_lobula_posts.npz` | LPLC2 の小葉と小葉板の後シナプスと、両神経叢の全列の中心 |
| `data/malecns/camera-map/cells.csv` | 細胞ごとの `type`、`body`、`side`、画像の `u` と `v`、後シナプス数 |

`u` は左端が 0、右端が 1 である。`v` は上が 0 である。これらも git には入らない。定量のノートは、この 2 つの npz を読む。

車に載せる表は、このキャッシュと loom 回路の辺から作る。列が同じ後シナプスは本数にまとめ、DNp01 への化学シナプス数を細胞ごとに付ける。出力は `src/flycar/loom_cells.npz` で、リポジトリに入れる。

```bash
python3 scripts/export_loom_cells.py
```

Janelia のバケットと NeuPrint から取り直す手順は以下である。

## NeuPrint の Token を入手

https://neuprint.janelia.org/ にアクセスし google アカウント連携などでログインする。
右上のアカウントアイコンから Account を開く。
Auth Token をリポジトリ直下の `.env` に書き込む。

```bash
export NEUPRINT_TOKEN=abcdefg.....
```

```bash
cd data/malecns
base=https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome

curl -L -C - -O "$base/body-annotations-male-cns-v1.0-minconf-0.5.feather"
curl -L -C - -O "$base/body-neurotransmitters-male-cns-v1.0.feather"
curl -L -C - -O "$base/connectome-weights-male-cns-v1.0-minconf-0.5.feather"
```

細胞種は MaleCNS の DNp01、looming の直接入力は LC4 と LPLC2 の 3 つ。

```bash
cd data/malecns
source ../../.env

curl -sS -X POST "https://neuprint.janelia.org/api/custom/custom" \
  -H "Authorization: Bearer $NEUPRINT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataset":"male-cns:v1.0","cypher":"MATCH (n:Neuron) WHERE n.type IN [\"LC4\",\"LPLC2\",\"DNp01\"] RETURN n.bodyId AS bodyId, n.type AS type, n.instance AS instance"}' \
  -o gf_loom.json
```

## Giant Fiber の loom 回路を切り出す

`scripts/extract_gf_loom.py` は、上でダウンロードした 3 つの feather から巨大線維の loom 逃避回路だけを切り出す。NeuPrint のトークンは使わない。リポジトリ直下で次を実行する。全結合約 1.5 億本を走査するので数分かかる。

```bash
python3 scripts/extract_gf_loom.py
```

依存は Python 3 の `numpy`、`pandas`、`pyarrow`。

### 残す細胞

loom の視覚入力は LC4 と LPLC2、巨大線維は DNp01（hemibrain 名は Giant Fiber）。そこから先の運動側も残す。TTMn は跳躍、PSI は飛翔開始、DLMn は背縦走筋の運動ニューロン。DLMn は片側 5 つで、筋線維 a+b を支配する 1 つと c–f を支配する 4 つ。

| 型 | 役割 (`role`) | 本数 |
|---|---|---|
| LC4 | `loom_vpn` | 左 71、右 55 |
| LPLC2 | `loom_vpn` | 左 94、右 91 |
| DNp01 | `giant_fiber` | 左右 1 |
| TTMn | `jump_motor` | 左右 1 |
| PSI | `flight_trigger` | 左右 1 |
| DLMn a, b / DLMn c-f | `flight_motor` | 左右 5 |

LC4 と LPLC2 は、すべて同側の DNp01 にだけ繋がる。光受容器や T4/T5 は入れない。刺激は LC4 と LPLC2 に入れる。

### 出力

`data/malecns/gf-loom/` に書く。再実行すると上書きする。

| ファイル | 内容 |
|---|---|
| `neurons.feather` | 327 細胞。`bodyId`、`type`、`instance`、`side`（`L`/`R`）、`role`、`consensus_nt`、`nt_sign`、細胞体座標 |
| `edges.feather` | 回路の内側だけの化学シナプス。`body_pre`、`body_post`、`weight`（シナプス数）、シナプス前の `consensus_nt` と `nt_sign` |
| `type_edges.csv` | 細胞型から細胞型へのシナプス数と辺の数 |
| `summary.json` | 左右別の経路、DNp01 の入出力上位、切り出しの注意 |

`nt_sign` はアセチルコリンが `+1`、GABA とグルタミン酸が `-1`。予測が `unclear` の PSI と DLMn は空欄で、符号は付かない。TTMn のグルタミン酸は神経筋接合の予測なので、中枢内の抑制としては使わない。

`weight` は信頼度 0.5 以上の化学シナプス数で、全部残してある。ノイズとして落とすなら 5 未満を除くと約 5,300 本になる。

### この表に無いもの

重みは化学シナプスだけである。GF どうし、GF から TTMn、GF から PSI の、行動を実際に駆動する結合は電気シナプスで、ここには無い。化学シナプスだけでは DNp01 から TTMn が 20 と 70、PSI が合計 16、左右の DNp01 どうしが各 1 しかない。最初のシミュレーションの出力は DNp01 の発火にする。

この切り出しには視野上の列番号は付いていない。列番号は `syn-points` にあり、画面への位置は [画面の列対応を作る](#画面の列対応を作る) が付ける。刺激を片眼の LC4 と LPLC2 全体に入れる古いノートは、右の LC4 が 55 対 71 と少ないままである。

GFC2、GFC3、GFC4 は巨大線維と電気的に結合する相手で、型の付いた化学出力としては大きいが、定義が電気シナプスなので入れていない。

## 走性のステア回路を切り出す

カメラ車では赤と青を別の部分グラフにする。青（loom 回避）は、上で切った LC4、LPLC2、DNp01 を使う。TTMn、PSI、DLMn は跳躍と飛翔の経路なので、ヨーの指令には使わない。赤（走性）は DNa02 だけで、`scripts/extract_steer_dna02.py` が別ディレクトリに書く。キノコ体、触角葉、T4、T5 は入れない。

```bash
python3 scripts/extract_steer_dna02.py
```

MaleCNS の注釈表から型 `DNa02` を取る。NeuPrint のトークンは要らない。全結合を 1 回走査する。

| ファイル | 内容 |
|---|---|
| `data/malecns/steer-dna02/neurons.feather` | DNa02 の左右 1 本。`role` は `steer_dn` |
| `data/malecns/steer-dna02/edges.feather` | 両端が DNa02 の化学シナプスだけ |
| `data/malecns/steer-dna02/type_edges.csv` | 左右の組み合わせごとのシナプス数 |
| `data/malecns/steer-dna02/summary.json` | 細胞、落とした loom 側との交差辺、使い方 |

赤は 2 本の DNa02 への外部電流にする。匂いの学習回路は切らない。車の走行則はこの表の外にある。概要は [システムの解説](../README.md#システムの解説)、式の全文は [poster/poster.md](../poster/poster.md)。DNa02 と LC4、LPLC2、DNp01 のあいだの辺は `summary.json` の `dropped_cross_with_loom` に本数だけ残し、`edges.feather` には書かない。2 つの `edges.feather` は結合しない。
