import cv2
# import torch
import pandas as pd
import time
# import paho.mqtt.client as mqtt
import mqtt_pub
import config
from datetime import datetime
import asyncio
from pathlib import Path
from ultralytics import YOLO

from hard_example import HardExampleDetector, pick_best_bbox
from sample_queue import SampleQueue
from upload_client import UploadClient


def setup_camera(): # カメラの初期化
    cap = cv2.VideoCapture(config.settings.CAMERA_ID)
    # カメラの解像度設定
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.settings.INFERENCE_IMAGE_SIZE)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.settings.INFERENCE_IMAGE_SIZE)
    return cap

async def detect_objects(model, frame, imgsz, conf=0.6, classes=None, verbose=False): # AIモデルを使ってフレームから物体を検出する関数
    conf = float(conf)
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) # グレースケールに変換してモデルに入力（YOLOは通常3チャンネルの画像を想定しているため、グレースケールを3チャンネルに変換）
    input_frame = cv2.merge([gray_frame, gray_frame, gray_frame]) # グレースケールを3チャンネルに変換
    results = model(input_frame, imgsz=imgsz, verbose=verbose, conf=conf, classes=classes) # モデルで物体検出を実行

    if results[0].boxes is None or len(results[0].boxes) == 0: # 検出結果がない場合は空のDataFrameを返す
        return pd.DataFrame(), results[0]

    # 検出結果をPandas DataFrameに変換
    df = pd.DataFrame(results[0].boxes.data.cpu().numpy(), columns=[ # YOLOの検出結果をDataFrameに変換
                      'xmin', 'ymin', 'xmax', 'ymax', 'confidence', 'class'])
    return df, results[0] # DataFrameとYOLOの結果オブジェクトを返す


def judgementElecator(df_elevator, model_elevator, max_conf): # エレベーターの表示内容と方向を判定する関数
    elevator_floor = 0 # エレベーターの表示内容（階数）を初期化
    direction = 0 # エレベーターの方向を初期化
    result_conf = 0.0 # エレベーターの検出結果
    
    if not df_elevator.empty: # エレベーターの検出結果がある場合
        # 全ての検出結果をループでチェックする
        for _, row in df_elevator.iterrows():
            class_id = int(row['class'])
            label = model_elevator.names[class_id]
            conf = row['confidence']

            # スコアが一番高いものをログ用の確信度にする
            if conf > max_conf:
                result_conf = conf

            # ラベルが数字（'9','10'など）か判定
            if label.isdigit():
                elevator_floor = label.strip()
            # ラベルが矢印（'up','down'）か判定
            
            if label in ['up', 'down']:
                direction = label
        return [elevator_floor, direction, result_conf]
    else:
        return [elevator_floor, direction, result_conf]


def _maybe_save_hard_example(
    detector: HardExampleDetector,
    queue: SampleQueue,
    uploader: UploadClient,
    frame,
    df_elevator,
    elevator_floor,
    direction,
    result_conf,
):
    if not config.settings.HARD_EXAMPLE_ENABLED:
        return

    rows = []
    if df_elevator is not None and not df_elevator.empty:
        rows = df_elevator.to_dict("records")
    bbox = pick_best_bbox(rows)
    has_detection = bool(rows)
    decision = detector.observe(
        floor=elevator_floor,
        direction=direction,
        confidence=result_conf,
        bbox=bbox,
        now=time.time(),
        has_detection=has_detection,
    )
    if not decision.is_hard:
        return

    result = queue.enqueue(
        frame,
        reason=decision.reason,
        confidence=decision.confidence,
        predicted_floor=elevator_floor,
        predicted_direction=direction,
        bbox=decision.bbox,
    )
    if result.saved and result.meta_path and result.image_path:
        upload = uploader.maybe_upload(result.meta_path, result.image_path)
        if upload.attempted and not upload.success:
            print(f"⚠️ hard-example upload failed: {upload.detail}")

    
async def main():
# def main():
    try:
        image_size = config.settings.INFERENCE_IMAGE_SIZE
        max_conf = 0.0 # エレベーターの検出結果の中で最も高い確信度を記録する変数
        person_conf = float(0.7) # 人物検出の信頼度の閾値を0.7に設定（誤検出を減らすため）
        elevator_conf = float(0.3) # エレベーターの数字・矢印検出の信頼度の閾値を0.3に設定（小さめにして見逃しを減らすため）
        client_id="elevator_publisher"
        headless = bool(config.settings.HEADLESS)
        interval_sec = float(config.settings.INFERENCE_INTERVAL_SEC)

        detector = HardExampleDetector(
            conf_low=config.settings.HARD_CONF_LOW,
            conf_high=config.settings.HARD_CONF_HIGH,
            miss_frames=config.settings.HARD_MISS_FRAMES,
            min_interval_sec=config.settings.HARD_MIN_INTERVAL_SEC,
            floor_jump_threshold=config.settings.HARD_FLOOR_JUMP_THRESHOLD,
        )
        queue = SampleQueue(
            root_dir=Path(config.settings.HARD_EXAMPLE_DIR),
            daily_budget_bytes=config.settings.DAILY_UPLOAD_BUDGET_BYTES,
            jpeg_quality=config.settings.HARD_JPEG_QUALITY,
            max_long_edge=config.settings.HARD_MAX_LONG_EDGE,
            device_id=config.settings.DEVICE_ID,
        )
        uploader = UploadClient(
            enabled=config.settings.UPLOAD_ENABLED,
            url=config.settings.UPLOAD_URL,
            timeout_sec=config.settings.UPLOAD_TIMEOUT_SEC,
        )
        
        print("--- 🚀 リアルタイム監視システム起動 ---")
        print(f"HEADLESS={headless} INFERENCE_INTERVAL_SEC={interval_sec}")
        print(
            f"HARD_EXAMPLE_ENABLED={config.settings.HARD_EXAMPLE_ENABLED} "
            f"UPLOAD_ENABLED={config.settings.UPLOAD_ENABLED}"
        )
        # モデルの読み込み
        print("\n⏳ モデルをロードしています...")
        model_people =YOLO(config.settings.YOLO_AI_MODEL_PASS)  # 人物検出用のモデルをロード
        model_elevator = YOLO(config.settings.ELEVATOR_AI_MODEL_PASS)  # エレベーターの数字・矢印検出用のモデルをロード
        print("\n✅ モデルのロードに成功しました")

        print("\n⏳ カメラを初期化しています...")
        cap = setup_camera()
        print ("\n✅ カメラの初期化に成功しました")
        
        # MQTTクライアントの接続
        print("\n⏳ MQTTクライアントを接続しています...")
        
        client=mqtt_pub.connect_mqtt_publisher(client_id)
        
        if client is None or not client.is_connected(): 
            print("\n❌ MQTTクライアントの接続に失敗しました")
            print("\n ⏳ MQTTクライアントの再接続を試みます...")
            client=mqtt_pub.connect_mqtt_publisher(client_id)
            
        # time.sleep(2)  # 接続が安定するまで少し待つ
        
        # ログの見出しを表示
        print("\n" + "-" * 60)
        print(f"{'時刻':<10} | {'人数':<4} | {'表示内容':<15} | {'方向'} | {'信用度'}")
        print("-" * 60)

        while cap.isOpened(): # カメラが開いているどうか
            try:
                # 2. エレベーター情報の取得（数字と矢印の両方に対応）
                elevator_floor = 0
                direction = 0
                ret, frame = await asyncio.get_event_loop().run_in_executor(None, cap.read) # カメラからフレームを読み込む
                if not ret:
                    print("❌ カメラからフレームを取得できませんでした。終了します。")
                    continue
                
                # --- AI検出実行 ---
                result =await asyncio.gather(
                    detect_objects(model_people, frame, imgsz=image_size, conf=person_conf, classes=[0]),  # クラス0は通常 'person'
                    detect_objects(model_elevator, frame, imgsz=image_size, conf=elevator_conf)  # エレベーターは全クラス対象
                )
                df_people, res_p = result[0] # 人物検出の結果
                df_elevator, res_e = result[1] # エレベーター検出の結果
                people_count = len(df_people) # 人数をカウント
                
                elevator_floor, direction, result_conf = judgementElecator(df_elevator, model_elevator, max_conf) # エレベーターの表示内容と方向を判定

                _maybe_save_hard_example(
                    detector,
                    queue,
                    uploader,
                    frame,
                    df_elevator,
                    elevator_floor,
                    direction,
                    result_conf,
                )
                
                # 3. ターミナルへのログ出力
                now = datetime.now()
                now_str = now.strftime(f"%Y/%m/%d  %H:%M:%S")
                print(f"{now_str} | {people_count}人 | {elevator_floor} | {direction} | {result_conf:.2f}")

                asyncio.gather(mqtt_pub.publish_elevator_status(client, config.settings.MQTT_TOPIC, config.settings.DEVICE_ID,elevator_floor,people_count,direction)) # MQTTでエレベーターの状態を送信

                if not headless:
                    display_floorwindow = f"{elevator_floor} ".strip()
                    annotated_frame = res_p.plot()
                    annotated_frame = res_e.plot(img=annotated_frame)
                    info_text = f"People: {people_count}  Floor: {display_floorwindow} direction: {direction}"
                    cv2.putText(
                        annotated_frame, info_text, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2
                    )
                    cv2.imshow("Real-time AI Monitor", annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                if interval_sec > 0:
                    await asyncio.sleep(interval_sec)
                
            except Exception as e:
                print(f"❌ エラー: {e}")
            except KeyboardInterrupt:
                print("\n--- ⌨️ キーボード割り込みで終了 ---")
                cap.release()
                if not headless:
                    cv2.destroyAllWindows()
                print("\n--- 👋 システムを終了しました ---")

        # 後片付け
        cap.release()
        if not headless:
            cv2.destroyAllWindows()
    except Exception as e:
        print(f"❌ エラー: {e}")
    except KeyboardInterrupt:
        print("\n--- ⌨️ キーボード割り込みで終了 ---")
        print("\n--- 👋 システムを終了しました ---")

if __name__ == "__main__":
    asyncio.run(main())
