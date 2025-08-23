# de-project
2025 Data Engineering Course Project



## 資料夾結構
```
de-project/
├── .venv/                                   # Python 虛擬環境
├── .gitignore                               # Git 忽略檔案設定
├── .python-version                          # Python 版本指定
├── README.md                                # 專案說明文件
├── pyproject.toml                           # Python 專案配置檔
├── uv.lock                                  # UV 套件管理鎖定檔
│
├── data_ingestion/                          # 🔥 核心資料擷取模組
│   ├── __init__.py                          # Python 套件初始化
│   ├── config.py                            # 配置檔（環境變數）
│   ├── worker.py                            # Celery Worker 設定
│   ├── tasks.py                             # Celery 任務定義
│   └── producer.py                          # 基本 Producer
│
└── docker-compose-broker.yml               # RabbitMQ Broker 配置
```



## 指令
```
# 建立虛擬環境並安裝依賴（同步）
uv sync

# 建立一個 network 讓各服務能溝通
docker network create my_network

# 啟動服務
docker compose -f docker-compose-broker.yml up -d

# 停止並移除服務
docker compose -f docker-compose-broker.yml down

＃ 查看服務 logs
docker logs -f rabbitmq
docker logs -f flower

# producer 發送任務
uv run data_ingestion/producer.py

# 啟動 worker
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker1%h
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker2%h


```