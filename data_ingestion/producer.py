from data_ingestion.tasks import crawler

for i in range(10):
    print(f"sent task{i} to broker")
    crawler.delay(x=f"task{i}")