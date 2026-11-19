import secrets,logging,math
from sqlalchemy import select,func
from fastapi import HTTPException
from redis import Redis
from ..config.settings import REDIS_URL,CONFIG
from ..models.run import Run
from ..models.record import Record
from ..models.attribution import Attribution
from ..models.comparison import Comparison
from ..utils.serialization import row,now
from .sources import source_or_404
from .audit import log
from . import permutation
queue=Redis.from_url(REDIS_URL)
DEFAULTS=CONFIG['compare_defaults']
def list_attributions(db,source_id):
    source_or_404(db,source_id)
    rows=[]
    for a in db.scalars(select(Attribution).where(Attribution.source_id==source_id).order_by(Attribution.version.desc())):
        d=row(a);d['bearings']=len(set(a.mapping.values()));d['samples']=len(a.mapping);rows.append(d)
    return rows
def create_attribution(db,user,source_id,data):
    """归属更正另出一版；旧版本保留，已启动的检验仍按原版计算。"""
    s=source_or_404(db,source_id);mapping=data.mapping
    if not mapping:raise HTTPException(422,'归属映射不能为空')
    if len(mapping)>20000:raise HTTPException(422,'归属映射条目过多')
    refs=set(db.scalars(select(Record.reference).where(Record.source_id==s.id)))
    cleaned={}
    for reference,bearing in mapping.items():
        if reference not in refs:raise HTTPException(422,'归属包含来源中不存在的样本编号：'+str(reference))
        bearing=str(bearing).strip()
        if not bearing or len(bearing)>120:raise HTTPException(422,'轴承归属需为1–120字符：'+str(reference))
        cleaned[reference]=bearing
    version=(db.scalar(select(func.max(Attribution.version)).where(Attribution.source_id==s.id)) or 0)+1
    a=Attribution(source_id=s.id,version=version,note=data.note.strip(),mapping=cleaned,created_at=now())
    db.add(a);db.flush();log(db,user,'attribution.created',a.id,f'v{version} · {len(cleaned)}条');db.commit()
    return row(a)
def get_comparison(db,id):
    c=db.get(Comparison,id)
    if not c:raise HTTPException(404,'未找到换位检验')
    return c
def list_comparisons(db):
    return [{k:v for k,v in row(c).items() if k!='prepared'} for c in db.scalars(select(Comparison).order_by(Comparison.id.desc()))]
def comparison_detail(db,id):
    return {k:v for k,v in row(get_comparison(db,id)).items() if k!='prepared'}
def create_comparison(db,user,data):
    a=db.get(Run,data.run_a_id);b=db.get(Run,data.run_b_id)
    if not a or not b:raise HTTPException(404,'未找到分析任务')
    if a.id==b.id:raise HTTPException(422,'请选择两项不同的研究')
    if a.state!='completed' or b.state!='completed':raise HTTPException(409,'仅可比较已完成的研究')
    if a.source_id!=b.source_id:raise HTTPException(422,'两项研究必须来自同一批次')
    fault_a,fault_b=data.fault_a.strip(),data.fault_b.strip()
    if fault_a==fault_b:raise HTTPException(422,'两类指定故障需不同')
    labels=set(a.result.get('labels',[]))&set(b.result.get('labels',[]))
    for fault in (fault_a,fault_b):
        if fault not in labels:raise HTTPException(422,'指定故障类型不在两项研究的共同标签中：'+fault)
    if data.attribution_version is not None:
        version=data.attribution_version
        if not db.scalar(select(Attribution.id).where(Attribution.source_id==a.source_id,Attribution.version==version)):
            raise HTTPException(404,f'未找到归属版本 v{version}')
    else:
        version=db.scalar(select(func.max(Attribution.version)).where(Attribution.source_id==a.source_id))
        if not version:raise HTTPException(422,'该批次还没有轴承归属版本，请先录入归属')
    samples=data.samples or DEFAULTS['samples']
    if not DEFAULTS['min_samples']<=samples<=DEFAULTS['max_samples']:
        raise HTTPException(422,f"换位抽样数需在{DEFAULTS['min_samples']}至{DEFAULTS['max_samples']}之间")
    name=(data.name or '').strip() or (a.name+' × '+b.name)[:150]
    c=Comparison(source_id=a.source_id,run_a_id=a.id,run_b_id=b.id,name=name,fault_a=fault_a,fault_b=fault_b,
                 attribution_version=version,state='queued',seed=secrets.randbelow(2**31),samples=samples,created_at=now())
    db.add(c);db.flush();log(db,user,'comparison.queued',c.id,name);db.commit()
    try:queue.rpush('comparison:queue',c.id)
    except Exception:
        c.state='failed';c.error='队列暂不可用，请重新创建任务';db.commit();raise HTTPException(503,c.error)
    return row(c)
def retry_comparison(db,user,id):
    """失败重试：保留已提交的批次进度，从断点继续，不重复计数。"""
    c=get_comparison(db,id)
    if c.state!='failed':raise HTTPException(409,'仅失败的换位检验可以重试')
    c.state='queued';c.error='';log(db,user,'comparison.retried',c.id,c.name);db.commit()
    try:queue.rpush('comparison:queue',c.id)
    except Exception:
        c.state='failed';c.error='队列暂不可用，请稍后重试';db.commit();raise HTTPException(503,c.error)
    return row(c)
def prepare(db,c):
    """配对两项研究的折外判读并冻结计算快照；此后归属更正不影响本任务。"""
    a=db.get(Run,c.run_a_id);b=db.get(Run,c.run_b_id)
    if not a or not b or a.state!='completed' or b.state!='completed':raise ValueError('两项研究的结果已不可用，停止计算')
    att=db.scalar(select(Attribution).where(Attribution.source_id==c.source_id,Attribution.version==c.attribution_version))
    if not att:raise ValueError(f'归属版本 v{c.attribution_version} 已不存在，停止计算')
    pairs=permutation.pair_rows(a.result['rows'],b.result['rows'],att.mapping,c.fault_a,c.fault_b,c.attribution_version)
    prepared=permutation.build_prepared(pairs,c.fault_a,c.fault_b,c.samples)
    prepared['attribution_version']=c.attribution_version
    return prepared
def execute_comparison(id):
    from ..config.database import Session
    with Session() as db:
        c=db.get(Comparison,id)
        if not c or c.state not in ('queued','running'):return
        c.state='running';db.commit()
        try:
            if not c.prepared:
                c.prepared=prepare(db,c);c.total_swaps=c.prepared['total_swaps'];c.done=0;c.hits=0
                db.commit()
            prepared=c.prepared;batches=math.ceil(c.total_swaps/prepared['batch_rows'])
            index=c.done//prepared['batch_rows']
            while index<batches:
                c.hits+=permutation.evaluate_batch(prepared,c.seed,index)
                c.done=min((index+1)*prepared['batch_rows'],c.total_swaps)
                db.commit()
                index+=1
            c.result=permutation.finish(prepared,c.seed,c.hits);c.result['attribution_version']=c.attribution_version
            c.state='completed';log(db,'worker','comparison.completed',c.id)
        except Exception as e:
            logging.exception('comparison failed');c.state='failed';c.error=str(e)[:2000]
            log(db,'worker','comparison.failed',c.id,c.error)
        db.commit()
def interrupted_ids(db):
    """中断后按原版恢复：准备快照已冻结归属版本，重排队后从断点继续。"""
    return list(db.scalars(select(Comparison.id).where(Comparison.state=='running')))
