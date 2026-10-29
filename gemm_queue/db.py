from sqlalchemy import create_engine
from gemm_queue.config import settings

def createDbEngine(connectionUrl):
    engine = create_engine(connectionUrl, echo=True)
    return engine

dbEngine = createDbEngine(settings.database_url)

