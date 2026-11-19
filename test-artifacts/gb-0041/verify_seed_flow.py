"""种子演示全流程验证：seed 建库 → worker 消费两个队列 → 换位检验算齐并报告。

运行：cd backend && python ../test-artifacts/gb-0041/verify_seed_flow.py
"""
import os,sys,tempfile,json
from pathlib import Path
tmp=Path(tempfile.mkdtemp(prefix='seed-flow-'))
os.environ['DATABASE_URL']='sqlite:///'+str(tmp/'demo.db')
os.environ['ARTIFACT_DIR']=str(tmp/'artifacts')
os.environ['SEED_DEMO']='false'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from scripts.seed_demo import seed
from src.config.database import Session
from src.models.run import Run
from src.models.comparison import Comparison
from src.models.attribution import Attribution
from src.worker import execute,recover
from src.services.compare import execute_comparison
from sqlalchemy import select

class FakeQueue:
    def __init__(self):self.items=[]
    def rpush(self,key,value):self.items.append((key,int(value)))
    def ping(self):return True
import src.services.runs as runs_svc,src.services.compare as compare_svc
import scripts.seed_demo as seed_mod
import src.worker as worker_mod
fake=FakeQueue();runs_svc.queue=fake;compare_svc.queue=fake;seed_mod.queue=fake;worker_mod.queue=fake

seed();seed()  # 连跑两次，验证幂等不重复
with Session() as db:
    runs=db.scalars(select(Run).order_by(Run.id)).all()
    comparisons=db.scalars(select(Comparison)).all()
    attributions=db.scalars(select(Attribution)).all()
    assert len(runs)==2,f'应恰好两个种子研究，实际{len(runs)}'
    assert len(comparisons)==1,f'应恰好一个种子检验，实际{len(comparisons)}'
    assert len(attributions)==3 and all(a.version==1 for a in attributions)
    assert all(len(a.mapping)==240 and len(set(a.mapping.values()))==120 for a in attributions),'每批次240样本/120轴承'
# 按队列顺序消费：先两个研究，后换位检验
for key,payload in fake.items:
    if key=='analysis:queue':execute(payload)
    else:execute_comparison(payload)
with Session() as db:
    for r in db.scalars(select(Run)):assert r.state=='completed',(r.id,r.state,r.error)
    c=db.scalars(select(Comparison)).one()
    assert c.state=='completed',c.error
    res=c.result
    print(json.dumps({'概率':res['probability'],'换位总数':res['total_swaps'],'实测差':res['observed'],
                      '漏判':res['misses'],'模式':res['mode'],'轴承':res['bearings'],'配对':res['pairs']},ensure_ascii=False,indent=1))
    assert res['mode']=='sampled' and res['total_swaps']==c.samples==200000,'120轴承走分批抽样'
    assert res['pairs']==240 and res['bearings']==120
    assert 0<res['probability']<=1
# 中断恢复路径：把任务改回 running，recover 应重新排队且 execute 直接完成不重复计数
with Session() as db:
    c=db.scalars(select(Comparison)).one();c.state='running';db.commit()
before=len(fake.items)
recover()
assert len(fake.items)==before+1 and fake.items[-1]==('comparison:queue',c.id),'recover 应重排队 running 任务'
execute_comparison(fake.items[-1][1])
with Session() as db:
    c=db.scalars(select(Comparison)).one();assert c.state=='completed' and c.hits==c.result['hits'],'恢复后不重复计数'
print('seed flow ok')
