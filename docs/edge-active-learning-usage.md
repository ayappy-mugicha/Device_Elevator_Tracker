# エッジ能動学習 MVP 使い方

Raspberry Pi 上で難例をローカル収集し、省電力寄りに推論する MVP の使い方です。  
サーバー HTTPS は未対応のため、アップロードはデフォルト無効です。

関連:

- [運用・学習戦略](./edge-operation-and-learning.md)
- [サーバー機能要件](./server-active-learning-requirements.md)

---

## 1. セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
# .env を実機の MQTT / カメラ / モデルパスに合わせて編集
```

単体テスト:

```bash
python -m pytest tests -q
```

---

## 2. 主な設定（`.env`）

| 変数 | 既定 | 意味 |
|------|------|------|
| `INFERENCE_INTERVAL_SEC` | `0.5` | 推論間隔（秒）。大きいほど省電力 |
| `HEADLESS` | `false` | `true` で GUI（`imshow`）なし |
| `HARD_EXAMPLE_ENABLED` | `true` | 難例ローカル保存の有無 |
| `HARD_CONF_LOW` / `HARD_CONF_HIGH` | `0.25` / `0.65` | 迷っている確信度帯 |
| `HARD_MISS_FRAMES` | `5` | 連続見逃しで難例化 |
| `HARD_MIN_INTERVAL_SEC` | `3.0` | 難例保存の最短間隔 |
| `HARD_EXAMPLE_DIR` | `data/hard_examples` | 保存先 |
| `DAILY_UPLOAD_BUDGET_BYTES` | `5242880` (5MB) | 1日あたり保存バイト上限 |
| `UPLOAD_ENABLED` | `false` | サーバー送信（HTTPS 準備まで false） |
| `UPLOAD_URL` | 空 | 将来の `POST` 先 |

---

## 3. 実行

```bash
python ai.py
```

動作:

1. カメラ推論（人物 + エレベーター表示）
2. 変化時のみ MQTT で状態送信（従来どおり極小）
3. 難例と判定されたフレームは ROI JPEG + メタ JSON を `HARD_EXAMPLE_DIR` に保存
4. `UPLOAD_ENABLED=false` の間はローカルに残るだけ

推奨（バッテリ重視）:

```env
HEADLESS=true
INFERENCE_INTERVAL_SEC=1.0
```

---

## 4. 保存されるデータ

```text
data/hard_examples/
  images/*.jpg
  meta/*.json
  budget.json          # 当日の使用バイト
```

メタ JSON の主要フィールド: `device_id`, `timestamp`, `predicted_floor`, `predicted_direction`, `confidence`, `reason`, `bbox`, `image_relpath`。

`reason` の例:

- `uncertain_conf` — 確信度が低〜中
- `miss_streak` — 連続で表示を読めない
- `floor_jump` — 階が不自然に飛んだ

メンテ時はディレクトリごと回収し、サーバー側アノテに渡せます。

---

## 5. アップロードを有効にするとき

サーバーが [server-active-learning-requirements.md](./server-active-learning-requirements.md) を満たし **HTTPS** で受信できるまで無効のままにしてください。

```env
UPLOAD_ENABLED=true
UPLOAD_URL=https://example.com/api/v1/hard-examples
```

失敗時はローカルファイルを削除しません（再送・持ち出し可能）。

---

## 6. モジュール構成

| ファイル | 役割 |
|----------|------|
| `hard_example.py` | 難例判定 |
| `sample_queue.py` | ROI 保存と日次バイト予算 |
| `upload_client.py` | HTTP(S) アップロード骨組み |
| `ai.py` | 推論ループへの組み込み |
| `tests/` | 判定・予算・保存の単体テスト |
