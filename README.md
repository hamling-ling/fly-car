# Fly-Car

Arduino Uno Q Fly Car Project

## Preparation

### NeuPrint の Token を入手

https://neuprint.janelia.org/ にアクセスし google アカウント連携などでログインする。
右上のアカウントアイコン->[Account] をクリック
Auth Token を .env に書き込み

.env
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

細胞腫は  MaleCNS の DNp01、looming の直接入力は LC4 と LPLC2 の 3 つ。
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

視野上の列番号はこれらの細胞に付いていない。刺激は片眼ずつ、同側の LC4 と LPLC2 全体に入れる。右の LC4 は 55 対 71 と少ない。

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

赤の左右差は、2 本の DNa02 への外部電流の差にする。匂いの学習回路は切らない。青が閾値を超えたフレームでは DNa02 の出力を捨て、DNp01 の左右差だけを使う。その切り替えはこの表には入っておらず、シミュレーション側の規則である。DNa02 と LC4、LPLC2、DNp01 のあいだの辺は `summary.json` の `dropped_cross_with_loom` に本数だけ残し、`edges.feather` には書かない。2 つの `edges.feather` は結合しない。

カメラとモーターを使わない机上の走行は `notebooks/chemotaxis_sim.ipynb`。
