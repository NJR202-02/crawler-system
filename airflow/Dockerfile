# 使用 Ubuntu 22.04 作為基礎映像檔
FROM ubuntu:22.04

# 更新套件列表，並安裝必要的系統依賴
RUN apt-get update && \
    apt-get install -y \
        python3.10 \
        python3-pip \
        curl \
        && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 安裝 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
 && uv --version

# 建立 Airflow 工作目錄
RUN mkdir -p /opt/airflow

# 安裝 Airflow 2.10.4 及其所有依賴（包括 PostgreSQL、GCP 和 Docker）
RUN uv pip install --system "apache-airflow[google,docker,postgres]==2.10.4" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.10.txt"

# 強制安裝 PyMySQL（解決依賴衝突）
RUN uv pip install --system --force-reinstall pymysql==1.1.2

# 複製專案檔案到 Airflow 工作目錄
COPY ../pyproject.toml ../uv.lock ../README.md /opt/airflow/
COPY ../data_ingestion /opt/airflow/data_ingestion/

# 直接安裝專案依賴到系統環境（不建立虛擬環境）
RUN cd /opt/airflow && uv pip install --system -e .

# 設定時區和 Airflow 主目錄
ENV AIRFLOW_HOME=/opt/airflow

# 設定語系環境和時區
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=Asia/Taipei

# 設定 Airflow 工作目錄
WORKDIR /opt/airflow
