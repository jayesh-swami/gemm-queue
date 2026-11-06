from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gemm_queue.config import settings

def createDbEngine(connectionUrl):
    engine = create_engine(connectionUrl, echo=True)
    return engine

dbEngine = createDbEngine(settings.database_url)

# expire_on_commit=False so objects stay readable after the session closes
SessionLocal = sessionmaker(dbEngine, expire_on_commit=False)
