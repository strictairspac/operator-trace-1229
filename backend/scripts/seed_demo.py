from src.config.database import Base,engine,Session
from src.bootstrap import ensure_schema
from src.models.identity import User,Audit
from src.models.dataset import Dataset
from src.models.plan import Plan
from src.models.trace import Trace
from src.models.experiment import Experiment
from src.utils.security import hash_password
DEFAULT_STEPS=[{'op':'scan','source':'readings'},{'op':'filter','field':'value','compare':'gte','value':50},{'op':'hash_join','right':'sensors','left_key':'sensor_id','right_key':'sensor_id'},{'op':'group','keys':['zone'],'measure':'value','aggregate':'avg'}]
# 实验套分支计划：分组键必须含 sensor_id，产出 count/sum/avg 供下游当采样值
UPSTREAM_STEPS=[{'op':'scan','source':'readings'},{'op':'group','keys':['sensor_id'],'measure':'value','aggregate':'avg'}]
DOWNSTREAM_STEPS=[{'op':'scan','source':'readings'},{'op':'filter','field':'value','compare':'gte','value':10},{'op':'group','keys':['sensor_id'],'measure':'value','aggregate':'count'}]
def seed():
 ensure_schema()
 with Session() as s:
  for role in ('admin','operator','viewer'):
   if not s.query(User).filter_by(email=role+'@operator.local').first():s.add(User(email=role+'@operator.local',role=role,password=hash_password('Trace2026!')))
  sensors=[{'sensor_id':i,'zone':['北场','南场','试验间'][i%3],'device_type':['pump','motor','valve'][i%3]} for i in range(1,13)]
  readings=[{'sensor_id':i%12+1,'value':round(25+(i*13%800)/10,1),'recorded_at':f'2026-11-17T{8+i//60:02d}:{i%60:02d}:00'} for i in range(240)]
  seeds=[('松原日班温升采样',sensors,readings,'240条采样 / 12个传感器 / 区域温升复核'),('空数据边界',[],[],'验证空输入和空聚合'),('重复键校验',[{'sensor_id':1,'zone':'北场','device_type':'pump'},{'sensor_id':1,'zone':'复核点','device_type':'pump'}],[{'sensor_id':1,'value':80,'recorded_at':'2026-11-17T09:00:00'}],'右表重复键必须保留连接倍数')]
  for name,a,b,desc in seeds:
   if not s.query(Dataset).filter_by(name=name).first():s.add(Dataset(name=name,sensors=a,readings=b,description=desc))
  s.flush()
  for i,(name,_,_,_) in enumerate(seeds):
   pname=['过滤-连接-分组基线','空输入管线','重复键内连接'][i]
   if not s.query(Plan).filter_by(name=pname).first():s.add(Plan(name=pname,dataset_id=s.query(Dataset).filter_by(name=name).one().id,steps=DEFAULT_STEPS,note='受限DSL，Python算子真实执行',version=1))
  # 实验套演示：同数据集上的上游均值分支与下游计数分支
  base_ds=s.query(Dataset).filter_by(name='松原日班温升采样').one()
  up_name='实验-上游传感器均值';down_name='实验-下游高温计数'
  if not s.query(Plan).filter_by(name=up_name).first():s.add(Plan(name=up_name,dataset_id=base_ds.id,steps=UPSTREAM_STEPS,note='按传感器分组的 avg，作为下游采样',version=1))
  if not s.query(Plan).filter_by(name=down_name).first():s.add(Plan(name=down_name,dataset_id=base_ds.id,steps=DOWNSTREAM_STEPS,note='对上游 avg 采样再过滤计数',version=1))
  s.commit()
  _seed_experiment(s,base_ds.id,up_name,down_name)
  counts={m.__tablename__:s.query(m).count() for m in (User,Dataset,Plan,Trace,Experiment)};print(counts);return counts
def _seed_experiment(s,ds_id,up_name,down_name):
 from src.services import experiments
 from src.schemas.business import BranchInput,ExperimentInput
 if s.query(Experiment).filter_by(name='实验套-温升依赖演示').first():return
 up=s.query(Plan).filter_by(name=up_name).one();down=s.query(Plan).filter_by(name=down_name).one()
 payload=ExperimentInput(name='实验套-温升依赖演示',dataset_id=ds_id,branches=[
  BranchInput(node_key='upstream',plan_id=up.id,depends_on=[],measure='avg'),
  BranchInput(node_key='downstream',plan_id=down.id,depends_on=['upstream'],measure='avg')])
 try:experiments.create(payload)
 except Exception as exc:print('experiment seed skipped:',exc)
if __name__=='__main__':seed()
