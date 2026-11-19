import json,time,logging
from redis import Redis
from sqlalchemy import select
from .config.database import Session
from .config.settings import REDIS_URL,ARTIFACT_DIR
from .models.run import Run
from .models import source,record,user,note,audit,attribution,comparison
from .services.algorithm import calculate
from .services.audit import log
from .services.export import csv_response
from .services.compare import execute_comparison,interrupted_ids
queue=Redis.from_url(REDIS_URL)
ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
def execute(id):
    with Session() as db:
        r=db.get(Run,id)
        if not r or r.state!='queued':return
        r.state='running';db.commit()
        try:
            result=calculate(r.snapshot['records'],r.parameters)
            json.dumps(result,allow_nan=False)
            r.result=result;r.state='completed'
            response=csv_response(result,'run.csv')
            (ARTIFACT_DIR/f'run-{r.id}.csv').write_bytes(response.body)
            log(db,'worker','run.completed',r.id)
        except Exception as e:
            logging.exception('analysis failed');r.state='failed';r.error=str(e)[:2000]
            log(db,'worker','run.failed',r.id,r.error)
        db.commit()
def recover():
    """worker重启后恢复中断的换位检验：准备快照已冻结归属版本，从断点批次继续。"""
    with Session() as db:
        ids=interrupted_ids(db)
    for id in ids:
        try:queue.rpush('comparison:queue',id)
        except Exception:logging.exception('comparison recover failed')
def main():
    recover()
    while True:
        (ARTIFACT_DIR/'heartbeat').write_text(str(time.time()))
        value=queue.blpop(['analysis:queue','comparison:queue'],timeout=2)
        if value:
            key=value[0].decode() if isinstance(value[0],bytes) else value[0]
            if key=='comparison:queue':execute_comparison(int(value[1]))
            else:execute(int(value[1]))
if __name__=='__main__':main()
