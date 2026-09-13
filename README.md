README.md
Markdown
# Elevator Tracker System

エレベーター内の様子をAI（YOLOv5）で解析し、リアルタイムで物体の検知・追跡、およびその結果をMQTTで配信するシステムです。

## プロジェクト構成

- `ai.py`: 推論エンジンおよびメインロジック（難例キュー・HEADLESS対応）。
- `hard_example.py` / `sample_queue.py` / `upload_client.py`: エッジ能動学習 MVP。
- `mqtt_pub.py`: 検知したデータを外部システムへ送信する MQTT パブリッシャー。
- `config.py`: カメラ・MQTT・難例収集などの設定管理。
- `.env.example`: 環境変数のテンプレート。
- `docs/edge-active-learning-usage.md`: 能動学習 MVP の使い方。
- `docs/server-active-learning-requirements.md`: サーバー側機能要件（HTTPS 準備後）。

## 特徴

- **カスタムAIモデル**: エレベーター内の特定の状況を検知するために最適化されたモデルを使用。
- **リアルタイム通信**: MQTTプロトコルを使用し、低遅延で検知結果を通知。
- **柔軟な設定**: `config.py` または `.env` ファイルにより、環境ごとの設定変更が容易。
- **能動学習（MVP）**: 難例 ROI をローカル保存（アップロードはデフォルト無効）。

## セットアップ

### 1. 依存関係のインストール

Python 3.8以上を推奨します。

```bash
pip install -r requirements.txt
```

### 2. 環境設定

`.env.example` をコピーして `.env` を作成し、必要な情報を記入します。

```bash
cp .env.example .env
```

### 3. 実行

```bash
python ai.py
```

### 4. テスト

```bash
python -m pytest tests -q
```

詳細な使い方は [docs/edge-active-learning-usage.md](docs/edge-active-learning-usage.md) を参照してください。

更新履歴
2026/02/19: 最新アップデート（リポジトリ情報に基づく）


---

### 補足
リポジトリ内に詳細なドキュメントがなかったため、ファイル構成から一般的な構成を推測して作成しています。
- **`Elevator_Trackerv5.pt`** はPyTorchの重みファイルであるため、実行には `torch` および `ultralytics` (YOLO) のライブラリが必要になる可能性が高いです。
- **MQTT**を使用しているため、動作確認には Mosquitto などのブローカーが必要です。