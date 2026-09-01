# World Generator — H3 to VR

文章から、画像生成モデルと MiniMax H3 を組み合わせて **VRで閲覧できる空間**を作るための実行可能なMVPです。

このプロジェクトは「動画をVR動画として貼る」だけではありません。次の処理を一つのパイプラインにしています。

```text
自然言語
  ↓
WorldIR（固定形状・移動可能領域・カメラ軌道・再構成制約）
  ↓
GPT Image 2：正面アンカー画像 + 任意の360°パノラマ
  ↓
MiniMax H3：カットなし・低速・静的シーンのカメラ移動動画
  ↓
COLMAP / Nerfstudio Splatfacto：カメラ姿勢推定 + 3D Gaussian Splat再構成
  ↓
Spark + Three.js + WebXR：ブラウザ / VRヘッドセット向けビューア
```

## 現在できること

- 日本語または英語のプロンプトから、再構成向けの `WorldIR` を生成
- OpenAI `gpt-image-2` で、H3の開始フレームとなる整合性重視の画像を生成
- MiniMax H3 V2 APIで4〜15秒のI2VA動画を生成
- H3-Context-IRを任意で利用
- 動画をNerfstudio `splatfacto` でGaussian Splatへ再構成
- `.ply` をSparkで表示するWebXRビューアを自動生成
- 再構成失敗時にも空間を確認できる360°パノラマWebXRフォールバック
- APIキーやGPUなしで、全プロンプトと実行計画を検証する `--dry-run`
- 外部APIを呼ばないユニットテストとGitHub Actions CI

## 重要な前提

H3は高品質な音声付き動画生成モデルですが、現時点のH3出力は、厳密なカメラ姿勢・深度・多視点幾何を直接保証する3D表現ではありません。そのため、生成動画からのCOLMAP姿勢推定やGaussian Splat再構成は、シーンによって失敗します。

本実装は成功率を上げるため、次を強制します。

- 一つの連続ショット
- 低速かつ小〜中振幅のカメラ移動
- 固定焦点距離、固定露出、固定ホワイトバランス
- 人物・動物・煙・水面などの動的要素を原則排除
- 建築、家具、物体数、材質、照明を動画全体で固定
- カット、ズーム、被写界深度変化、モーフィング、モーションブラーを禁止

これでも再構成できない場合は、同じ世界用に作った360°パノラマをWebXR空間として出力します。

## セットアップ

### 1. Python環境

```bash
git clone https://github.com/dj-thank/World-generator-.git
cd World-generator-
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[openai]"
cp .env.example .env
```

`.env` に以下を設定します。

```dotenv
OPENAI_API_KEY=...
MINIMAX_API_KEY=...
```

### 2. 3D再構成環境

Nerfstudio、COLMAP、FFmpegを別途インストールします。GPUがない環境では `--panorama-only` または `--dry-run` が使えます。

コマンドが通るか確認します。

```bash
worldgen doctor
```

## 使い方

### 実行計画だけ作る

API課金やGPU処理を行わず、WorldIRと全プロンプトを生成します。

```bash
worldgen generate \
  "雨上がりの未来的な神社。濡れた石畳、木造と発光ガラスの融合、参拝者はいない" \
  --output outputs/cyber-shrine \
  --dry-run
```

### H3動画からGaussian SplatとWebXRを作る

```bash
worldgen generate \
  "海を見下ろす静かな白い地中海風の中庭。中央に歩ける石床、固定された家具、人物なし" \
  --output outputs/courtyard \
  --duration 10 \
  --resolution 768P \
  --camera-path arc-clockwise \
  --orbit-degrees 45
```

H3-Context-IRを使う場合:

```bash
worldgen generate "巨大な静かな宇宙船の展望室" \
  --output outputs/observation-room \
  --use-context-ir
```

### 既存画像をH3の開始フレームに使う

```bash
worldgen generate "この空間を静的なまま、カメラだけが右へ回り込む" \
  --anchor-image ./room.png \
  --output outputs/room
```

### パノラマだけ生成する

```bash
worldgen generate "苔に覆われた静かな地下庭園" \
  --output outputs/garden \
  --panorama-only
```

### 既存動画を再構成する

```bash
worldgen reconstruct ./capture.mp4 --output outputs/reconstructed
```

### ビューアを起動する

```bash
worldgen serve outputs/courtyard/viewer-splat --port 8000
```

ブラウザで `http://localhost:8000` を開きます。対応端末では「Enter VR」が表示されます。デスクトップではクリック後にWASDで移動できます。

## 出力

```text
outputs/courtyard/
├── manifest.json
├── world-ir.json
├── prompts/
│   ├── anchor-image.txt
│   ├── panorama-image.txt
│   └── h3-video.txt
├── media/
│   ├── anchor.png
│   ├── panorama.png
│   └── h3-video.mp4
├── reconstruction/
│   ├── processed/
│   ├── training/
│   ├── export/
│   └── world.ply
├── viewer-splat/
│   ├── index.html
│   └── assets/world.ply
└── viewer-panorama/
    ├── index.html
    └── assets/panorama.png
```

## 設計上の判断

- **768Pが既定値**: 2Kは映像品質を上げますが、姿勢推定成功率を自動的に保証するわけではなく、生成費用と処理量が増えます。
- **H3-Context-IRは任意**: このリポジトリ自身が再構成特化の構造化プロンプトを作るため、既定では無効です。自由形式の参照素材を増やす場合に有効化できます。
- **Gaussian Splatを主出力**: メッシュ化よりも、生成映像の細かな見た目を維持しやすく、WebXR表示までの距離が短いためです。
- **パノラマを必ず残す**: 3D再構成に失敗しても、世界コンセプトと没入表示を失わないためです。

詳しい構成は [docs/architecture.md](docs/architecture.md)、H3をカメラ条件付きワールドモデルへ追加学習する計画は [docs/training-roadmap.md](docs/training-roadmap.md) を参照してください。

## テスト

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## セキュリティと費用

- APIキーは `.env` のみに置き、Gitへコミットしないでください。
- ローカル画像はMiniMax APIへData URLとして送信できますが、大きい素材は公開期限付きURLの利用を推奨します。
- `generate` はOpenAI画像生成、MiniMax H3生成、任意のContext-IRを呼ぶため、実行前に各サービスの料金を確認してください。
- `--dry-run` は外部APIを一切呼びません。

## ライセンス

このリポジトリの独自コードはMIT Licenseです。MiniMax H3、OpenAI API、Nerfstudio、COLMAP、Spark、Three.jsにはそれぞれ別のライセンス・利用規約が適用されます。特にH3のCommunity Licenseには地域、売上、表示、用途、生成出力を学習に使う場合の条件があります。詳細は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を確認してください。
