import time
import random

from data_ingestion.worker import app


# 註冊 task, 有註冊的 task 才可以變成任務發送給 rabbitmq
@app.task()
def crawler(x):
    print(f"execute task: {x}...")
    time.sleep(random.randint(1, 10))  # 模擬處理時間
    print(f"{x} done.")
