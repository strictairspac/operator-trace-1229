from sqlalchemy import Column,Integer,String,JSON,ForeignKey
from src.config.database import Base
class Plan(Base):
 __tablename__='plans'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 dataset_id=Column(Integer,ForeignKey('datasets.id'),nullable=False)
 steps=Column(JSON,nullable=False)
 note=Column(String(500),nullable=False,default='')
 # 每次保存产生新版本；实验套分支引用受理时的版本，计划后续修改不影响在途实验
 version=Column(Integer,nullable=False,default=1,server_default='1')
