# de-project
2025 Data Engineering Course Project

## 🏗️ 專案架構概述

本專案是一個完整的資料工程管道，整合了多個現代化的資料處理工具：

- **🕷️ 資料擷取**: 使用 Python 爬蟲技術擷取 Hahow 線上課程平台資料
- **⚡ 任務調度**: 透過 Celery + RabbitMQ 實現分散式任務處理
- **🚀 工作流程管理**: 使用 Apache Airflow 進行 ETL 流程編排
- **🗄️ 資料存儲**: MySQL 資料庫儲存結構化資料
- **📊 資料視覺化**: Metabase 建立商業智慧儀表板
- **🐳 容器化部署**: Docker & Docker Compose 統一管理服務

### 資料流程
```
Hahow 網站 → Python 爬蟲 → RabbitMQ → Celery Workers → MySQL → Metabase
                ↑                                                    ↓
            Airflow DAG                                         商業智慧報表
```

## 資料夾結構
```
de-project/
├── .venv/                                   # Python 虛擬環境
├── .gitignore                               # Git 忽略檔案設定
├── .python-version                          # Python 版本指定
├── README.md                                # 專案說明文件
├── pyproject.toml                           # Python 專案配置檔
├── uv.lock                                  # UV 套件管理鎖定檔
├── Dockerfile                               # Docker 映像檔配置
│
├── data_ingestion/                          # 🔥 核心資料擷取模組
│   ├── __init__.py                          # Python 套件初始化
│   ├── config.py                            # 配置檔（環境變數）
│   ├── worker.py                            # Celery Worker 設定
│   ├── tasks.py                             # Celery 任務定義
│   ├── producer.py                          # 基本 Producer
│   ├── mysql.py                             # MySQL 連線模組
│   ├── crawler.py                           # 爬蟲基礎模組
│   │
│   ├── # Hahow 爬蟲相關模組
│   ├── hahow_crawler_common.py              # Hahow 爬蟲共用函式
│   ├── hahow_crawler_course.py              # Hahow 課程爬蟲
│   ├── hahow_crawler_course_optimized.py    # Hahow 課程爬蟲優化版
│   ├── hahow_crawler_course_optimized_sales.py # Hahow 課程銷售爬蟲
│   ├── hahow_crawler_article.py             # Hahow 文章爬蟲
│   ├── hahow_crawler_article_optimized.py   # Hahow 文章爬蟲優化版
│   │
│   ├── # Producer 相關模組
│   ├── producer_crawler_hahow_all.py        # Hahow 全部資料 Producer
│   ├── producer_crawler_hahow_by_queue.py   # Hahow 分隊列 Producer
│   ├── producer_crawler_hahow_course.py     # Hahow 課程 Producer
│   │
│   └── # Tasks 相關模組
│       ├── tasks_crawler_hahow_course.py    # Hahow 課程爬蟲任務
│       └── tasks_crawler_hahow_article.py   # Hahow 文章爬蟲任務
│
├── airflow/                                 # 🚀 Apache Airflow 工作流程管理
│   ├── airflow.cfg                          # Airflow 配置檔
│   ├── Dockerfile                           # Airflow Docker 映像檔
│   ├── docker-compose-airflow.yml           # Airflow Docker Compose 配置
│   ├── logs/                                # Airflow 執行日誌
│   ├── plugins/                             # Airflow 自訂外掛
│   └── dags/                                # Airflow DAG 工作流程定義
│       ├── example_first_dag.py             # 基礎範例 DAG
│       ├── example_dummy_tasks_dag.py       # 虛擬任務範例 DAG
│       ├── example_parallel_dag.py          # 並行任務範例 DAG
│       ├── hahow_crawler_dag.py             # Hahow 爬蟲 DAG
│       └── hahow_crawler_producer_dag.py    # Hahow Producer DAG
│
│
├── example/                                 # 📚 SQL 範例與查詢
│   ├── employees.sql                        # 員工資料表範例
│   ├── students.sql                         # 學生資料表範例
│   ├── ecommerce.sql                        # 電商資料表範例
│   └── course_sales_queries.sql             # 課程銷售查詢範例
│
├── output/                                  # 📁 輸出資料目錄
│   ├── hahow_course_*.csv                   # Hahow 課程資料
│   └── hahow_article_*.csv                  # Hahow 文章資料
│
└── # Docker Compose 配置檔案
    ├── docker-compose-broker.yml            # RabbitMQ Broker 配置
    ├── docker-compose-mysql.yml             # MySQL 資料庫配置
    ├── docker-compose-producer.yml          # Producer 服務配置
    └── docker-compose-worker.yml            # Worker 服務配置
```



## 指令

### 🔧 環境設定
```bash
# 建立虛擬環境並安裝依賴（同步）
uv sync

# 建立一個 network 讓各服務能溝通
docker network create my_network
```

### 🌍 環境變數設定
本專案使用純 Python 實現自動載入 `.env` 檔案中的環境變數，無需額外套件，類似 pipenv 的行為。

### 🔄 載入環境變數的方法

**方法一：使用 uv 內建功能**
```bash
uv run --env-file .env data_ingestion/producer.py
uv run --env-file .env celery -A data_ingestion.worker worker --loglevel=info
```
- ✅ uv 原生支援
- ✅ 明確指定環境變數來源
- ✅ 不污染系統環境

**方法二：使用 source 載入**
```bash
source .env
uv run data_ingestion/producer.py
uv run celery -A data_ingestion.worker worker --loglevel=info
```
- ✅ 最簡單的方式
- ⚠️ 會影響當前 shell 環境

**方法三：直接在終端載入**
```bash
# 方式 1: 使用 source（最簡單）
source .env
python data_ingestion/hahow_crawler_article_optimized.py

**特色功能：**
- ✅ 彈性選擇：多種方式適應不同需求
- ✅ 預設值：如果 `.env` 不存在或變數未設定，使用程式碼預設值  
- ✅ 開發友善：類似 pipenv 的使用體驗

### 📊 Metabase 商業智慧儀表板
```bash
# 啟動 Metabase 服務（包含 PostgreSQL）
docker compose -f metabase/docker-compose-metabase.yml up -d

# 停止 Metabase 服務
docker compose -f metabase/docker-compose-metabase.yml down

# 查看 Metabase 服務狀態
docker compose -f metabase/docker-compose-metabase.yml ps

# 存取 Metabase 網頁介面
# http://localhost:3000
```

### 🚀 Apache Airflow 工作流程管理
```bash
# 啟動 Airflow 服務
docker compose -f airflow/docker-compose-airflow.yml up -d

# 停止 Airflow 服務
docker compose -f airflow/docker-compose-airflow.yml down

# 查看 Airflow 服務狀態
docker compose -f airflow/docker-compose-airflow.yml ps

# 查看 Airflow 服務日誌
docker compose -f airflow/docker-compose-airflow.yml logs -f

# 存取 Airflow 網頁介面
# http://localhost:8080
# 預設帳號密码: airflow / airflow
```

### 🔥 RabbitMQ Broker 與 Celery Worker
```bash
# 啟動 RabbitMQ Broker 服務
docker compose -f docker-compose-broker.yml up -d

# 停止並移除 RabbitMQ 服務
docker compose -f docker-compose-broker.yml down

# 查看服務 logs
docker logs -f rabbitmq
docker logs -f flower

# 存取 RabbitMQ 管理介面: http://localhost:15672 (guest/guest)
# 存取 Flower 監控介面: http://localhost:5555
```

### 🗄️ MySQL 資料庫
```bash
# 啟動 MySQL 服務
docker compose -f docker-compose-mysql.yml up -d

# 停止 MySQL 服務
docker compose -f docker-compose-mysql.yml down
```

### 🕷️ 爬蟲與任務執行
```bash
# 一次載入，多次使用
source .env

# Producer 發送任務
uv run data_ingestion/producer.py
uv run data_ingestion/producer_crawler_hahow_all.py
uv run data_ingestion/producer_crawler_hahow_by_queue.py
uv run data_ingestion/producer_crawler_hahow_course.py

# 啟動 Worker
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker1%h
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker2%h

# 指定 Worker concurrency
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker1%h --concurrency=1
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker2%h --concurrency=1

# 指定 Worker queue
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker1%h -Q hahow_course
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker2%h -Q hahow_article
uv run celery -A data_ingestion.worker worker --loglevel=info --hostname=worker3%h -Q hahow_course,hahow_article
```

### 🐳 Docker Compose 服務管理
```bash
# 啟動所有相關服務
docker compose -f docker-compose-broker.yml up -d
docker compose -f docker-compose-mysql.yml up -d
docker compose -f airflow/docker-compose-airflow.yml up -d
docker compose -f metabase/docker-compose-metabase.yml up -d

# 停止所有服務
docker compose -f docker-compose-broker.yml down
docker compose -f docker-compose-mysql.yml down
docker compose -f airflow/docker-compose-airflow.yml down
docker compose -f metabase/docker-compose-metabase.yml down

# 查看所有容器狀態
docker ps -a
```