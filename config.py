from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# プロジェクトのルートディレクトリを指定
BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    """ 環境変数を管理するためのPydanticモデル """

    # MQTT接続情報
    MQTT_HOST: str
    MQTT_PORT: int
    MQTT_TOPIC: str
    DEVICE_ID: str
    CAMERA_ID: int
    TRAIN_IMAGE_SIZE: int
    INFERENCE_IMAGE_SIZE: int
    YOLO_AI_MODEL_PASS: str
    ELEVATOR_AI_MODEL_PASS: str

    # Edge power / display
    INFERENCE_INTERVAL_SEC: float = 0.5
    HEADLESS: bool = False

    # Hard-example active learning (local queue)
    HARD_EXAMPLE_ENABLED: bool = True
    HARD_CONF_LOW: float = 0.25
    HARD_CONF_HIGH: float = 0.65
    HARD_MISS_FRAMES: int = 5
    HARD_MIN_INTERVAL_SEC: float = 3.0
    HARD_FLOOR_JUMP_THRESHOLD: int = 2
    HARD_EXAMPLE_DIR: str = str(BASE_DIR / "data" / "hard_examples")
    DAILY_UPLOAD_BUDGET_BYTES: int = 5 * 1024 * 1024
    HARD_JPEG_QUALITY: int = 70
    HARD_MAX_LONG_EDGE: int = 320

    # Upload stub (disabled until server HTTPS is ready)
    UPLOAD_ENABLED: bool = False
    UPLOAD_URL: str = ""
    UPLOAD_TIMEOUT_SEC: float = 30.0

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), # .envファイルの場所を指定
        extra='ignore' # 定義されていない環境変数があっても無視する
    )

# 設定をアプリケーション全体で利用できるようにインスタンス化
settings = Settings()
