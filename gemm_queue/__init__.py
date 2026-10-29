from gemm_queue.db import dbEngine
from sqlalchemy import text

def main() -> None:
    
    with dbEngine.connect() as conn:
        result = conn.execute(text("SELECT 'Hello World!'"))
        print(result.all())
