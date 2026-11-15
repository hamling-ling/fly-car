# システム構成

![システム構成図](./top.png)

# ハードウェアコンポーネント
```mermaid
flowchart TB
  pack["モバイルバッテリー"]
  hub["ASUS USB Type-C Hub"]
  cam["Sunplus 2K AutoFocus Webcam"]
  uno["Arduino UNO Q"]
  aa["単三乾電池 4 本"]
  smc["FEETECH FT-SMC-2CH"]
  right["FEETECH FM90（右）"]
  left["FEETECH FM90（左）"]

  pack -->|給電| hub
  cam -->|USB| hub
  hub -->|USB-C。電源とホスト| uno
  aa -->|電源| smc
  uno -->|右の信号 D3| smc
  uno -->|左の信号 D5| smc
  uno -->|GND| smc
  smc -->|出力| right
  smc -->|プラスとマイナスは逆| left
```

部品は次のとおりである。

| 部品 | 数量 | 備考 |
| --- | --- | --- |
| Arduino UNO Q | 1 | |
| Sunplus 2K AutoFocus Webcam | 1 | USB Web カメラ |
| ASUS USB Type-C Hub | 1 | |
| FEETECH FT-SMC-2CH | 1 | 2WD Mini Robot Mobile Platform Kit |
| FEETECH FM90 |2 | 2WD Mini Robot Mobile Platform Kit |
| モバイルバッテリー | 1 | |
| 単三乾電池 | 4 | |


# ソフトウェアコンポーネント

主要クラスのクラス図を記載する。

```mermaid
classDiagram
  direction TB

  namespace Python App {
    class Camera
    class Face

    class Color
    class Loom
    class Plant
    class Pulses
  }
  namespace MCUSketch {
    class Motors
    class Matrix
    class Lamps
  }
  Color "1" *-- "1" Loom
  Color ..> Camera
  Plant ..> Color
  Pulses ..> Plant
  Face ..> Color
  Face ..> Pulses
  Pulses ..> Motors : Bridge
  Face ..> Matrix : Bridge
  Face ..> Lamps : Bridge
```

各クラスの役割は次のとおりである。

| クラス | 役割 |
| --- | --- |
| Camera | 最新の 1 枚を置く |
| Color | 左右の眼の赤と青を数える |
| Loom | 青の拡大から電流を出す |
| Plant | 膜と車輪のフィルタを進める |
| Pulses | 速さをパルスにする |
| Face | 絵とランプの色を決める |
| Motors | パルスを車輪に書く |
| Matrix | 点マトリクスを灯す |
| Lamps | RGB を灯す |

# データフロー

```mermaid
flowchart TB
  subgraph grab [カメラ]
    eye["Sunplus 2K。別スレッドが最新の 1 枚を置く"]
  end
  subgraph pre [色の周期ごと]
    halves["左右の眼の範囲。中央で重なる"]
    redL["赤・左"]
    redR["赤・右"]
    blue["細胞の伸ばした位置の縦一列。視角と拡大"]
  end
  subgraph cells [膜の周期ごと。遅れた分は上限まで]
    dnaL["DNa02 左"]
    dnaR["DNa02 右"]
    dnpL["DNp01 左"]
    dnpR["DNp01 右"]
  end
  subgraph drive [車輪]
    law["赤は両輪を前へ。青は反対側だけ"]
    guard["赤が左右の範囲とも満ちていれば速度 0"]
    pulse["wheel_pulses。右、左のパルス"]
    mcu["スケッチ。右が D3、左が D5"]
  end
  face["点マトリクスと RGB。占有と、送ったパルス"]
  eye --> halves
  halves --> redL
  halves --> redR
  halves --> blue
  redL --> dnaL
  redR --> dnaR
  blue --> dnpL
  blue --> dnpR
  dnaL --> law
  dnaR --> law
  dnpL --> law
  dnpR --> law
  law --> guard
  guard --> pulse
  pulse --> mcu
  redL --> face
  redR --> face
  halves --> face
  pulse --> face
```

# シーケンス

```mermaid
sequenceDiagram
  participant App
  participant Camera
  participant Color
  participant Loom
  participant Plant
  participant Pulses
  participant Face
  participant Motors
  participant Matrix
  participant Lamps

  loop main.loop
  opt count period
    App->>Camera: shot
    Camera-->>App: frame
    App->>Color: update
    Color->>Loom: update
    Loom-->>Color: current
  end
  opt membrane period
    App->>Plant: steps
    Plant-->>App: speeds
    App->>Pulses: wheel_pulses
    Pulses-->>App: pulses
    App->>Motors: setMotorSpeed
  end
  opt new count
    App->>Face: frame and lamps
    Face-->>App: picture
    App->>Matrix: showFace
    App->>Lamps: showLamps
  end
  end
```


# 数理モデル

1. カメラ画像から電流を計算
    - 逃避の電流=α(拡大の強さ×同側LC4の青の割合+視角の大きさ×同側LPLC2の青の割合)
    - 接近の電流=α(同側の赤のPN−β×反対側の赤のPN)
2. 膜電位の時間発展
    - V←V+⊿t(-V+I)/τ
    - r=Vの発火率
3. モーターへの指令に変換
    - 左モーターへの指令=k(右接近発火率 - 右逃避の発火率)
    - 右モーターへの指令=k(左接近発火率 - 左逃避の発火率)

フルバージョンは Github リポジトリ中の [poster.md](https://github.com/hamling-ling/fly-car/blob/main/poster/poster.md) をご覧ください。

# まとめ

コネクトームと生物学的知見に基づくモデルにより、赤（接近）・青（逃避）の単純な視覚入力から、ハエの接近・逃避に対応するロボット動作を実現・確認し、神経の接続と細胞特性を反映した実装例を提示しました。
