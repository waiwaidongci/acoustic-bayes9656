import json,random,logging
from sqlalchemy import select,func
from src.config.database import Base,engine,Session
from src.config.settings import CONFIG
from src.models.user import User
from src.models.source import Source
from src.models.record import Record
from src.models.run import Run
from src.models.attribution import Attribution
from src.models.comparison import Comparison
from src.models import note,audit
from src.utils.security import hash_password
from src.utils.serialization import now
from src.services.runs import queue
from src.services.domain_validation import validate_record

def seed_values(kind,index,batch,rng):
    if kind=='gaussian':
        cls=index%3;return {'rms':round(max(.1,rng.gauss([1.2,3.0,2.0][cls]+batch*.08,.35)),3),'centroid':round(max(100,rng.gauss([900,1600,2300][cls],170)),2),'kurtosis':round(max(.1,rng.gauss([2.8,5.2,3.9][cls],.45)),3),'label':['正常','轴承磨损','转子偏心'][cls]}
    if kind=='density':
        cls=index%3
        if index%19==0:return {'temperature':round(rng.uniform(12,42),2),'humidity':round(rng.uniform(12,92),2),'particles':round(rng.uniform(4,140),2)}
        return {'temperature':round(rng.gauss([19,26,32][cls]+batch*.3,.8),2),'humidity':round(rng.gauss([72,45,28][cls],2.5),2),'particles':round(max(.1,rng.gauss([22,48,85][cls],3)),2)}
    if kind=='transition':
        choices=[['序章','材料','工艺','案例'],['序章','案例','附录'],['材料','工艺','案例','附录'],['序章','材料','案例'],['序章']]
        path=choices[rng.randrange(len(choices))];return {'session':f'SY-{batch+1}-{index+1:04}','path':'>'.join(path)}
    if kind=='forest':
        moisture=rng.uniform(20,60);thickness=rng.uniform(1,8);temperature=rng.uniform(50,100);airflow=rng.uniform(1,5)
        minutes=12+1.6*moisture+8*thickness-.45*temperature-3*airflow+0.1*moisture*thickness+rng.gauss(0,3)
        return {'moisture':round(moisture,2),'thickness':round(thickness,2),'temperature':round(temperature,2),'airflow':round(airflow,2),'minutes':round(max(5,minutes),2)}
    if kind=='neighbors':
        uid=index//6;slot=index%6;exhibit=(uid%3*3+slot)%12
        return {'visitor':f'V{uid+1:03}','exhibit':f'E{exhibit+1:02}','rating':round(max(1,min(5,3+(1 if exhibit%3==uid%3 else -.4)+rng.gauss(0,.55))),1)}

def counts(db):
    return {cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in (User,Source,Record,Run,Attribution,Comparison)}
def seed():
    Base.metadata.create_all(engine);rng=random.Random(42);queued=[];queued_comparisons=[]
    with Session() as db:
        for role in ('admin','analyst','viewer'):
            email=role+'@'+CONFIG['slug']+'.demo'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password_hash=hash_password('Research2026!'),role=role))
        for batch in range(3):
            key=CONFIG['code']+f'-202611-{batch+1:02}'
            source=db.scalar(select(Source).where(Source.key==key))
            if not source:
                source=Source(key=key,name=key+' '+['秋季常规组','复测对照组','工艺观察组'][batch],filename=CONFIG['slug']+f'-202611-{batch+1:02}.csv',description=CONFIG['scenario']);db.add(source);db.flush()
            for index in range(CONFIG['seed_count']):
                reference=key+f'-{index+1:04}'
                vals=seed_values(CONFIG['algorithm'],index,batch,rng)
                if not db.scalar(select(Record.id).where(Record.source_id==source.id,Record.reference==reference)):
                    db.add(Record(source_id=source.id,reference=reference,values=validate_record(vals)))
            db.flush()
            if not db.scalar(select(Attribution.id).where(Attribution.source_id==source.id,Attribution.version==1)):
                refs=[r.reference for r in db.scalars(select(Record).where(Record.source_id==source.id).order_by(Record.id))]
                mapping={ref:f'{key}-B{(i//2)+1:03}' for i,ref in enumerate(refs)}
                db.add(Attribution(source_id=source.id,version=1,note='初始归属：相邻两条样本同轴承',mapping=mapping,created_at=now()))
            if batch==0 and not db.scalar(select(Run.id).where(Run.name=='首轮种子研究')):
                records=[{'id':r.id,'source_id':r.source_id,'reference':r.reference,'values':r.values} for r in db.scalars(select(Record).where(Record.source_id==source.id).order_by(Record.id))]
                run=Run(source_id=source.id,name='首轮种子研究',state='queued',parameters=CONFIG['default_parameters'],snapshot={'source':{'id':source.id,'name':source.name,'filename':source.filename},'records':records},created_at=now());db.add(run);db.flush();queued.append(run.id)
            if batch==0 and not db.scalar(select(Run.id).where(Run.name=='首轮对照研究')):
                records=[{'id':r.id,'source_id':r.source_id,'reference':r.reference,'values':r.values} for r in db.scalars(select(Record).where(Record.source_id==source.id).order_by(Record.id))]
                run=Run(source_id=source.id,name='首轮对照研究',state='queued',parameters={'folds':5,'smoothing':CONFIG['default_parameters']['smoothing']},snapshot={'source':{'id':source.id,'name':source.name,'filename':source.filename},'records':records},created_at=now());db.add(run);db.flush();queued.append(run.id)
        db.commit();print(json.dumps(counts(db),ensure_ascii=False))
        with Session() as db2:
            if not db2.scalar(select(Comparison.id).where(Comparison.name=='首轮漏判换位检验')):
                ra=db2.scalar(select(Run).where(Run.name=='首轮种子研究'));rb=db2.scalar(select(Run).where(Run.name=='首轮对照研究'))
                first=db2.scalar(select(Source).where(Source.key==CONFIG['code']+'-202611-01'))
                if ra and rb and first and db2.scalar(select(Attribution.id).where(Attribution.source_id==first.id,Attribution.version==1)):
                    c=Comparison(source_id=first.id,run_a_id=ra.id,run_b_id=rb.id,name='首轮漏判换位检验',fault_a='轴承磨损',fault_b='转子偏心',attribution_version=1,state='queued',seed=20261101,samples=CONFIG['compare_defaults']['samples'],created_at=now())
                    db2.add(c);db2.flush();queued_comparisons.append(c.id);db2.commit()
    for id in queued:
        try:queue.rpush('analysis:queue',id)
        except Exception:logging.exception('seed queue unavailable')
    for id in queued_comparisons:
        try:queue.rpush('comparison:queue',id)
        except Exception:logging.exception('seed queue unavailable')
if __name__=='__main__':seed()
