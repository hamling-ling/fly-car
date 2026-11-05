# Fly-Car

オスのショウジョウバエのコネクトームから、カメラの赤と青で走る車をつくる。

## 必要な環境

### Linux と Python

シミュレーションは Linux 上の Python 3.12 で確認している。使うパッケージは `numpy`、`matplotlib`、`japanize-matplotlib`、`pandas`、`pyarrow`、`pytest`、`jupyter` である。`pandas` と `pyarrow` はコネクトームの切り出しと、結合表を読むノートだけで使う。

### Arduino Uno Q

実機は Arduino Uno Q。OS は Debian 13、Python は 3.13。シミュレーションだけならボードは要らない。

### Web カメラ

目の代わりは Logitech Brio 100。対角視野は製品仕様の 58°、取り込みの既定は 1280×720 である。画角のシミュレーションはこの仕様の数字だけを使い、カメラ本体は要らない。撮影の実験では、給電できる USB ハブの先にカメラを置く。

## Preparation

### リポジトリの clone

```bash
git clone https://github.com/hamling-ling/fly-car.git
cd fly-car
```

### Python 環境のセットアップ

```bash
python3 -m pip install numpy matplotlib japanize-matplotlib pandas pyarrow pytest jupyter
```

パッケージ `flycar` は `src/flycar` にある。`pytest` は `pyproject.toml` の `pythonpath` でそこを読む。ノートは同じ `src` を `sys.path` に足す。

### コネクトームの切り出し

結合表の入手、NeuPrint からの取り直し、loom 回路と DNa02 回路の切り出し、LC4 と LPLC2 の画面対応は [scripts/README.md](scripts/README.md) に書いた。画角のシミュレーションと `pytest` は、この表が無くても動く。

## Quick Start

### シミュレーションを動かす

リポジトリ直下で、車輪の固定フレームと基準の画角を確認する。

```bash
python3 -m pytest tests/test_behavior.py tests/test_fov.py
```

絵を見るときは `research/notebooks/fov_sim.ipynb` を開く。球の位置を変えるのは `research/notebooks/fov_scenes.ipynb`。どちらもコネクトームの表は読まない。結合そのものを積分するのは `research/notebooks/gf_loom_sim.ipynb` と `research/notebooks/chemotaxis_sim.ipynb` で、先に [切り出し](scripts/README.md) を済ませる。

ノートはリポジトリ直下か `research/notebooks/` から開く。

### 実機で動かす

本番のアプリは `src/flycar_q/`。起動は [src/flycar_q/README.md](src/flycar_q/README.md)。カメラのフレームを 0.10 秒ごとに読む。赤は左右の占有、青は視角と拡大速度にして、0.02 秒ごとに `Plant.steps` を呼んでパルスをマイコンへ送る。色の範囲は `src/flycar/color_thresholds.json` にあり、`occupancy.py` が読む。`research/color_capture_q/fit_thresholds.py` が色紙の4点からこのファイルを書く。床での走行と、m/s からパルスへの倍率は、まだ合わせていない。ラジコンとモーターの確認は `research/` に残してある。マイコンへ渡す左右の指令をその場で入れるアプリは [research/motor_adjust/README.md](research/motor_adjust/README.md)。直進に揃えた上限、マイコンへ送った指令、前進と後退の生値は [research/notebooks/straight_limits.ipynb](research/notebooks/straight_limits.ipynb)。ラジコンのページでは、その折れ線を右から左への変換としてオンにできる。`src/flycar_q` は送信直前に、同じ折れ線で左の指令を置き換える。

## 内容物

### シミュレーション

| 場所 | 内容 |
|---|---|
| `src/flycar/behavior.py` | 半画面の赤と青から、左右の車輪速度。`Plant.steps` は 20 ms 分 |
| `src/flycar/occupancy.py` | カメラ画像の赤と青の半画面占有。下限は隣の `color_thresholds.json` |
| `src/flycar/pulse.py` | 車輪の m/s をサーボのパルスにする |
| `src/flycar/fov.py` | 地面の球をカメラへ投影し、車を進める |
| `src/flycar/view.py` | 俯瞰、カメラ、ニューロンの図 |
| `research/notebooks/fov_sim.ipynb` | 基準の 1 場面 |
| `research/notebooks/fov_scenes.ipynb` | 球の位置を変えた場面 |
| `research/notebooks/gf_loom_sim.ipynb` | loom 回路の結合と DNp01 |
| `research/notebooks/chemotaxis_sim.ipynb` | 赤と青の机上走行。車輪則はノート側に別にある |
| `tests/` | 固定フレームと基準場面 |

### 実機を使ったキャプチャの実験

Uno Q に Brio 100 を載せて 1 枚取る手順は [research/camera_capture_q/README.md](research/camera_capture_q/README.md)。スクリプトは `research/camera_capture_q/capture.py`。色の見本をボタンでフォルダに分けるアプリは [research/color_capture_q/README.md](research/color_capture_q/README.md)。

### 本番の車

| 場所 | 内容 |
|---|---|
| `src/flycar_q/` | Uno Q に載せるアプリ。カメラ、膜、車輪 |

## システムの解説

画素から左右の車輪までの式は [poster/poster.md](poster/poster.md) に書いた。ここでは、電流と車輪の指令だけを置く。

赤の画素は同側の LPLC2 の重みを通り、DNa02 の電流になる。青の領域の拡大は同側の LC4 の重みを通り、DNp01 の電流になる。膜は左右の DNa02 と左右の DNp01 の四本で、互いにはつながない。左の車輪は右の二本の発火率を見、右の車輪は左の二本を見る。赤の発火率は車輪を前へ動かし、青の発火率は車輪を後へ動かす。

ゲイン $\alpha$ は、その側の刺激の平均が 1 で発火率が基準のとき、電流を 1 にする。重み付きの平均 $F$ は、その細胞種の同側のシナプスで取る。拡大の強さ $s(\dot\theta)$ は、視角の変化 $\dot\theta$ に掛かる。発火率 $r$ と、赤と青に共通の係数 $k$ から、左右の指令 $u_L$ と $u_R$ を作る。

$$
I^{\mathrm{DNa02}}_{L,R}=\alpha F^{\mathrm{LPLC2}}_{L,R}
$$

$$
I^{\mathrm{DNp01}}_{L,R}=\alpha s(\dot\theta) F^{\mathrm{LC4}}_{L,R}
$$

$$
u_L=k\left(r^{\mathrm{DNa02}}_R-r^{\mathrm{DNp01}}_R\right)
$$

$$
u_R=k\left(r^{\mathrm{DNa02}}_L-r^{\mathrm{DNp01}}_L\right)
$$

膜の積分と、指令を車輪速度にならす式は、ポスター原稿にある。結合表を細胞ごとに積分するのは `research/notebooks/gf_loom_sim.ipynb` である。

`src/flycar` が車輪を出すときは、半画面の赤の占有と、青の視角・拡大を四本の膜に入れる。起動と周期は [src/flycar_q/README.md](src/flycar_q/README.md) に書いた。
