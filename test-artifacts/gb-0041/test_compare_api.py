"""换位检验 HTTP 全流程集成测试：真实登录、建批、两次研究、归属版本、检验执行、断点重试。

运行：cd backend && python -m pytest ../test-artifacts/gb-0041/test_compare_api.py -q
"""
import os,sys,tempfile,importlib
from pathlib import Path
tmp=Path(tempfile.mkdtemp(prefix='compare-api-'))
os.environ['DATABASE_URL']='sqlite:///'+str(tmp/'test.db')
os.environ['ARTIFACT_DIR']=str(tmp/'artifacts')
os.environ['SEED_DEMO']='false'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from fastapi.testclient import TestClient
from src.config.database import Base,engine,Session
from src.models.user import User
from src.models.run import Run
from src.models.comparison import Comparison
from src.utils.security import hash_password
from src.utils.serialization import now
from src.services import compare,runs
from src.worker import execute
from src.services.compare import execute_comparison
import src.services.permutation as permutation

class FakeQueue:
    def __init__(self):self.items=[]
    def rpush(self,key,value):self.items.append((key,int(value)))
    def ping(self):return True
fake=FakeQueue();compare.queue=fake;runs.queue=fake

Base.metadata.create_all(engine)
with Session() as db:
    db.add(User(email='admin@t.demo',password_hash=hash_password('Research2026!'),role='admin'))
    db.add(User(email='viewer@t.demo',password_hash=hash_password('Research2026!'),role='viewer'))
    db.commit()
from src.main import app
client=TestClient(app)
def token(email):
    r=client.post('/auth/login',json={'email':email,'password':'Research2026!'});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}
ADMIN=token('admin@t.demo');VIEWER=token('viewer@t.demo')
F1,F2='轴承磨损','转子偏心'
def make_source():
    r=client.post('/sources',json={'name':'换位测试批次','filename':'cmp.csv','description':'集成测试'},headers=ADMIN);assert r.status_code==200,r.text
    sid=r.json()['id'];records=[]
    for i in range(24):
        cls=i%3
        records.append({'reference':f'R{i:03}','values':{'rms':[1.2,3.0,2.0][cls]+(i%5)*.01,'centroid':[900,1600,2300][cls]+i,'kurtosis':[2.8,5.2,3.9][cls],'label':['正常',F1,F2][cls]}})
    r=client.post(f'/sources/{sid}/records',json={'records':records},headers=ADMIN);assert r.status_code==200,r.text
    return sid
def make_run(sid,name,folds):
    r=client.post('/runs',json={'source_id':sid,'name':name,'parameters':{'folds':folds,'smoothing':1e-9}},headers=ADMIN);assert r.status_code==200,r.text
    rid=r.json()['id'];execute(rid)
    with Session() as db:assert db.get(Run,rid).state=='completed'
    return rid
def test_full_flow():
    sid=make_source();ra=make_run(sid,'研究甲',3);rb=make_run(sid,'研究乙',5)
    r=client.get(f'/sources/{sid}/attributions',headers=VIEWER);assert r.json()==[]
    mapping={f'R{i:03}':f'B{i//2:02}' for i in range(24)}
    r=client.post(f'/sources/{sid}/attributions',json={'mapping':mapping,'note':'初始归属'},headers=VIEWER);assert r.status_code==403
    r=client.post(f'/sources/{sid}/attributions',json={'mapping':mapping,'note':'初始归属'},headers=ADMIN);assert r.status_code==200,r.text
    assert r.json()['version']==1
    r=client.post(f'/sources/{sid}/attributions',json={'mapping':{**mapping,'R000':'B99'},'note':'归属更正'},headers=ADMIN)
    assert r.json()['version']==2,'归属更正另出一版'
    r=client.get(f'/sources/{sid}/attributions',headers=VIEWER);vs=r.json()
    assert [v['version'] for v in vs]==[2,1] and vs[1]['bearings']==12
    bad=dict(mapping);del bad['R023']
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2,'attribution_version':3},headers=ADMIN);assert r.status_code==404
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F1},headers=ADMIN);assert r.status_code==422
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':'不存在的故障'},headers=ADMIN);assert r.status_code==422
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':ra,'fault_a':F1,'fault_b':F2},headers=ADMIN);assert r.status_code==422
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2,'samples':5},headers=ADMIN);assert r.status_code==422
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2},headers=VIEWER);assert r.status_code==403
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2,'attribution_version':1,'name':'集成换位检验'},headers=ADMIN)
    assert r.status_code==200,r.text;cid=r.json()['id']
    assert r.json()['attribution_version']==1 and r.json()['state']=='queued'
    assert ('comparison:queue',cid) in fake.items
    execute_comparison(cid)
    r=client.get(f'/comparisons/{cid}',headers=VIEWER);assert r.status_code==200,r.text
    job=r.json();assert job['state']=='completed',job.get('error')
    res=job['result'];assert res['attribution_version']==1,'中断/完成后仍按原版归属'
    assert res['mode']=='exact' and res['total_swaps']==1<<12 and res['pairs']==24 and res['bearings']==12
    assert 0<res['probability']<=1 and res['hits']<=res['total_swaps']
    assert res['observed']==max(abs(res['misses']['a'][F1]-res['misses']['b'][F1]),abs(res['misses']['a'][F2]-res['misses']['b'][F2]))
    listed=client.get('/comparisons',headers=VIEWER).json()
    assert 'prepared' not in listed[0],'列表不携带准备快照大字段'
    assert listed[0]['result']['total_swaps']==res['total_swaps'],'列表携带小体积结果供页面报告'
    assert 'prepared' not in job
def test_stop_conditions_and_retry():
    sid=make_source()
    rows_a=[{'reference':f'R{i:03}','actual':F1,'predicted':F1,'posterior':.9} for i in range(24)]
    rows_b=[{'reference':f'R{i:03}','actual':F1 if i else F2,'predicted':F1,'posterior':.8} for i in range(24)]
    with Session() as db:
        db.add(Run(source_id=sid,name='甲',state='completed',parameters={},snapshot={},result={'labels':[F1,F2],'rows':rows_a},created_at=now()))
        db.add(Run(source_id=sid,name='乙',state='completed',parameters={},snapshot={},result={'labels':[F1,F2],'rows':rows_b},created_at=now()))
        db.commit()
        ra,rb=db.scalar(__import__('sqlalchemy').select(Run.id).where(Run.name=='甲')),db.scalar(__import__('sqlalchemy').select(Run.id).where(Run.name=='乙'))
    client.post(f'/sources/{sid}/attributions',json={'mapping':{f'R{i:03}':'B1' for i in range(24)},'note':'v1'},headers=ADMIN)
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2},headers=ADMIN);cid=r.json()['id']
    execute_comparison(cid)
    with Session() as db:
        job=db.get(Comparison,cid);assert job.state=='failed' and '真值不符' in job.error,'真值不符即停算'
    r=client.post(f'/comparisons/{cid}/retry',headers=ADMIN);assert r.status_code==200
    execute_comparison(cid)
    with Session() as db:
        job=db.get(Comparison,cid);assert job.state=='failed' and '真值不符' in job.error,'确定性停算可重试且结论一致'
    with Session() as db:
        b=db.get(Run,rb);b.result={'labels':[F1,F2],'rows':[dict(r,actual=F1) for r in rows_b]};db.commit()
    r=client.post(f'/sources/{sid}/attributions',json={'mapping':{f'R{i:03}':f'B{i//2}' for i in range(23)},'note':'缺一条归属'},headers=ADMIN)
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2,'attribution_version':2},headers=ADMIN);cid2=r.json()['id']
    execute_comparison(cid2)
    with Session() as db:
        job=db.get(Comparison,cid2);assert job.state=='failed' and '缺轴承归属' in job.error and 'v2' in job.error,'缺轴承归属即停算'
def test_interrupted_resume_no_double_count():
    sid=make_source();ra=make_run(sid,'续算甲',3);rb=make_run(sid,'续算乙',4)
    client.post(f'/sources/{sid}/attributions',json={'mapping':{f'R{i:03}':f'B{i//2:02}' for i in range(24)},'note':'v1'},headers=ADMIN)
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2},headers=ADMIN);cid=r.json()['id']
    execute_comparison(cid)
    with Session() as db:
        done=db.get(Comparison,cid);expected_hits=done.hits;expected=done.result['probability'];seed=done.seed
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2},headers=ADMIN);cid2=r.json()['id']
    with Session() as db:
        j=db.get(Comparison,cid2);j.seed=seed;j.samples=done.samples;db.commit()
    calls={'n':0};original=permutation.evaluate_batch;row_cap=permutation.ROW_CAP
    permutation.ROW_CAP=1024  # 缩小单批上限，强制分4批计算
    def flaky(prepared,s,index):
        calls['n']+=1
        if calls['n']==2:raise RuntimeError('模拟中断')
        return original(prepared,s,index)
    compare.permutation.evaluate_batch=flaky
    try:
        execute_comparison(cid2)
    finally:
        compare.permutation.evaluate_batch=original
    with Session() as db:
        j=db.get(Comparison,cid2);assert j.state=='failed' and 0<j.done<j.total_swaps and j.hits>0,'中断时保留已提交批次'
        partial_done,partial_hits=j.done,j.hits
    r=client.post(f'/comparisons/{cid2}/retry',headers=ADMIN);assert r.status_code==200
    try:
        execute_comparison(cid2)
    finally:
        permutation.ROW_CAP=row_cap
    with Session() as db:
        j=db.get(Comparison,cid2)
        assert j.state=='completed' and j.hits==expected_hits and j.result['probability']==expected,'断点续算不重复计数，结果与一次性算齐一致'
        assert j.done==j.total_swaps and partial_hits<=j.hits and partial_done<j.done
def test_version_freeze_while_running():
    sid=make_source();ra=make_run(sid,'版本甲',3);rb=make_run(sid,'版本乙',6)
    client.post(f'/sources/{sid}/attributions',json={'mapping':{f'R{i:03}':f'B{i//2:02}' for i in range(24)},'note':'v1'},headers=ADMIN)
    r=client.post('/comparisons',json={'run_a_id':ra,'run_b_id':rb,'fault_a':F1,'fault_b':F2},headers=ADMIN);cid=r.json()['id']
    client.post(f'/sources/{sid}/attributions',json={'mapping':{f'R{i:03}':'ONE' for i in range(24)},'note':'归属更正'},headers=ADMIN)
    execute_comparison(cid)
    with Session() as db:
        j=db.get(Comparison,cid)
        assert j.state=='completed' and j.attribution_version==1 and j.result['attribution_version']==1,'归属另出新版后仍按原版算齐'
        assert j.result['bearings']==12
