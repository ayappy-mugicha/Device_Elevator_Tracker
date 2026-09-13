# サーバー側：能動学習パイプライン機能要件定義

本書はエッジ（Raspberry Pi）側 MVP がローカル保存する難例データを受け取り、教師あり追加学習まで進めるための **サーバー機能要件** です。  
現状、本番サーバーは **HTTPS 未対応** のため実装対象外です。HTTPS が使えるようになってから本要件に沿って実装してください。

関連文書: [edge-operation-and-learning.md](./edge-operation-and-learning.md)

---

## 1. 目的

| 項目 | 内容 |
|------|------|
| 目的 | エッジから届く難例（ROI 画像 + メタデータ）を収集し、アノテーション〜 fine-tune 〜配布判定まで行う |
| 非目的（当面） | 強化学習、エッジ上学習、セルラー経由の頻繁なフルモデル配信 |
| 前提 | エッジは `UPLOAD_ENABLED=false` 既定。サーバー HTTPS 準備後に有効化する |

---

## 2. 現状と移行条件

### 現状

- エッジは難例を `data/hard_examples/{images,meta}/` にローカル保存する
- `upload_client.py` は HTTP(S) multipart POST の骨組みのみ（デフォルト無効）
- サーバー側の受信・学習・配布 API は **未実装**

### HTTPS 移行条件（実装開始のゲート）

- [ ] サーバーが TLS 終端可能な公開 URL を持つ
- [ ] 端末認証（API キーまたは端末証明書）の方針が決まっている
- [ ] 月次/日次の受信容量上限が運用上合意されている（Plan-D 500MB を意識）

ゲート未達の間は、メンテ時に SD / 有線 / Wi-Fi で `data/hard_examples` を持ち出す運用でよい。

---

## 3. エッジが送る契約（MVP 互換）

### 3.1 メタデータ JSON（`meta` パート）

エッジのローカル JSON と同一スキーマを受信すること。

| フィールド | 型 | 必須 | 説明 |
|------------|----|------|------|
| `sample_id` | string | yes | 一意 ID |
| `device_id` | string | yes | 端末 ID（例: E001） |
| `timestamp` | string (ISO8601) | yes | 取得時刻 |
| `predicted_floor` | string \| number | no | エッジ予測階 |
| `predicted_direction` | string \| number | no | `up` / `down` / 0 |
| `confidence` | number | yes | 0〜1 |
| `reason` | string | yes | `uncertain_conf` / `miss_streak` / `floor_jump` 等 |
| `bbox` | number[4] \| null | no | xmin, ymin, xmax, ymax |
| `image_relpath` | string | no | ローカル相対パス（参考） |
| `image_bytes` | number | no | JPEG バイト数 |
| `extra` | object | no | 拡張用 |

### 3.2 画像（`image` パート）

- Content-Type: `image/jpeg`
- ROI 切り出し済み・長辺縮小済みを想定（例: 長辺 320、品質 70）
- フルフレーム連続受信は要件外（拒否してよい）

### 3.3 転送方式（推奨）

`POST /api/v1/hard-examples`  
`multipart/form-data`:

- `meta`: application/json
- `image`: image/jpeg

将来拡張: メタのみ先行 POST → サーバーが必要な `sample_id` だけ画像再取得。

---

## 4. 機能要件一覧

### FR-01 受信 API

- 難例メタ + ROI 画像を受け付ける
- `device_id` + `sample_id` で冪等（再送で二重保存しない）
- 認証ヘッダ必須（未認証は 401）

### FR-02 容量ガード

- 端末別・全体の **日次 / 月次バイト上限** を超えたら 429 または 403
- 上限値は設定可能（エッジの `DAILY_UPLOAD_BUDGET_BYTES` と整合）

### FR-03 永続化

- 画像とメタをオブジェクトストレージまたはディスクに保存
- アノテーション状態（pending / labeled / rejected）を保持

### FR-04 アノテーション連携

- pending 一覧の取得
- YOLO 形式ラベルの登録（クラスは現場定義に固定）
- 検証セットへの誤混入防止（検証 ID は学習ジョブから除外）

### FR-05 学習ジョブ

- 現行最良重みからの fine-tune 起動
- エポック上限・早期終了・入力サイズを指定可能
- 成果物: 学習用 `.pt`（保管）+ 配布用小さい `.onnx`

### FR-06 配布ゲート

- 固定検証セットで旧モデルと比較
- 合格条件を満たさないモデルは配布候補に載せない
- 配布は原則 **非セルラー経路**（メンテ Wi-Fi / 有線）。セルラー配布は低頻度・小サイズのみ

### FR-07 監査ログ

- 受信・拒否理由・学習開始/終了・配布可否を記録

### FR-08 セキュリティ

- **HTTPS 必須**
- 端末認証、アップロードサイズ上限、レート制限
- 画像は機微情報としてアクセス制御

---

## 5. 非機能要件

| 項目 | 要件 |
|------|------|
| 可用性 | 受信 API はエッジ日次バッチに耐える（数分の停止は許容、再送前提） |
| 性能 | 単発アップロード数秒以内（低帯域 SIM 想定） |
| 運用 | 容量超過・学習失敗をアラート可能 |

---

## 6. 受け入れ条件（サーバー実装時）

- [ ] HTTPS で `POST /api/v1/hard-examples` がメタ+JPEG を保存できる
- [ ] 同一 `sample_id` 再送が二重登録にならない
- [ ] 日次予算超過で拒否できる
- [ ] pending → labeled → fine-tune → 検証ゲート → 配布候補の流れがドキュメントどおり動く
- [ ] エッジの `UPLOAD_ENABLED=true` + `UPLOAD_URL` 設定だけで送信試験ができる

---

## 7. エッジ側設定（サーバー準備後）

```env
UPLOAD_ENABLED=true
UPLOAD_URL=https://example.com/api/v1/hard-examples
UPLOAD_TIMEOUT_SEC=30
```

それまでは `UPLOAD_ENABLED=false` のまま、ローカルキューのみ使用する。
