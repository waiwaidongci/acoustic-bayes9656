from sqlalchemy import Column,Integer,BigInteger,String,JSON,Text,ForeignKey
from ..config.database import Base
from ..config.settings import CONFIG
class Comparison(Base):
    __tablename__=CONFIG['comparison_table']
    id=Column(Integer,primary_key=True)
    source_id=Column(Integer,ForeignKey(CONFIG['source_table']+'.id'),nullable=False)
    run_a_id=Column(Integer,ForeignKey(CONFIG['run_table']+'.id'),nullable=False)
    run_b_id=Column(Integer,ForeignKey(CONFIG['run_table']+'.id'),nullable=False)
    name=Column(String(160),nullable=False)
    fault_a=Column(String(120),nullable=False)
    fault_b=Column(String(120),nullable=False)
    attribution_version=Column(Integer,nullable=False)
    state=Column(String(20),default='queued')
    seed=Column(BigInteger,nullable=False)
    samples=Column(Integer,nullable=False)
    total_swaps=Column(BigInteger,default=0)
    done=Column(BigInteger,default=0)
    hits=Column(BigInteger,default=0)
    prepared=Column(JSON,nullable=True)
    result=Column(JSON,nullable=True)
    error=Column(Text,default='')
    created_at=Column(String(40),nullable=False)
