from sqlalchemy import Column,Integer,String,JSON,DateTime,ForeignKey,UniqueConstraint,func
from src.config.database import Base
class Experiment(Base):
 """一次实验套：若干相互依赖的计划分支组成的 DAG。"""
 __tablename__='experiments'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 dataset_id=Column(Integer,ForeignKey('datasets.id'),nullable=False)
 status=Column(String(20),nullable=False,default='running',server_default='running')
 definition=Column(JSON,nullable=False)       # 受理时的分支定义（plan_id/version/depends_on/measure）
 snapshot=Column(JSON,nullable=False)         # 受理时数据集与每个计划版本的不可变快照
 result=Column(JSON,nullable=True)            # 收齐并公开后的完整结果
 error=Column(String(1000),nullable=True)
 published=Column(Integer,nullable=False,default=0,server_default='0')
 created_at=Column(DateTime,server_default=func.now())
 published_at=Column(DateTime,nullable=True)
class ExperimentBranch(Base):
 """实验套内的一个计划分支（DAG 节点）。"""
 __tablename__='experiment_branches'
 id=Column(Integer,primary_key=True)
 experiment_id=Column(Integer,ForeignKey('experiments.id'),nullable=False)
 node_key=Column(String(80),nullable=False)
 plan_id=Column(Integer,ForeignKey('plans.id'),nullable=False)
 plan_version=Column(Integer,nullable=False)
 depends_on=Column(JSON,nullable=False)       # 上游节点 key 列表
 measure=Column(String(20),nullable=False)    # count/sum/avg，上游分组产出的采样列
 status=Column(String(20),nullable=False,default='blocked',server_default='blocked')
 result=Column(JSON,nullable=True)
 error=Column(String(1000),nullable=True)
 attempts=Column(Integer,nullable=False,default=0,server_default='0')
 created_at=Column(DateTime,server_default=func.now())
 updated_at=Column(DateTime,server_default=func.now(),onupdate=func.now())
 __table_args__=(UniqueConstraint('experiment_id','node_key',name='uq_branch_node_key'),)
