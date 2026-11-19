from sqlalchemy import Column,Integer,String,JSON,ForeignKey,UniqueConstraint
from ..config.database import Base
from ..config.settings import CONFIG
class Attribution(Base):
    __tablename__=CONFIG['attribution_table']
    __table_args__=(UniqueConstraint('source_id','version',name='uq_attribution_version'),)
    id=Column(Integer,primary_key=True)
    source_id=Column(Integer,ForeignKey(CONFIG['source_table']+'.id'),nullable=False)
    version=Column(Integer,nullable=False)
    note=Column(String(200),default='')
    mapping=Column(JSON,nullable=False)
    created_at=Column(String(40),nullable=False)
