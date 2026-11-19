"""单 worker 进程：线程池并发消费两类队列。

- operator-traces：原有单计划线性执行（单消费者语义保持不变）
- operator-experiments：实验套分支；互不依赖的分支在线程池内并发，
  下游等自己的上游全部 completed 后由调度解锁入队。
进程崩溃后的 running 任务不自动重试，由 bootstrap 标记为 failed 供人工重试。
"""
import os
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import redis

from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.trace import Trace
from src.services.operators import execute
from src.services.audit import log
from src.services import experiments
from src.bootstrap import ensure_schema

r = redis.Redis.from_url(REDIS_URL)
MAX_CONCURRENCY = int(os.getenv('BRANCH_CONCURRENCY', '3'))


def run_trace(run_id):
    with Session() as s:
        row = s.get(Trace, run_id)
        if not row or row.status != 'queued':
            return
        row.status = 'running'
        snapshot = row.snapshot
        s.commit()
    try:
        result = execute(snapshot['dataset'], snapshot['plan']['steps'])
        with Session() as s:
            tr = s.get(Trace, run_id)
            tr.result = result
            tr.status = 'completed'
            s.commit()
        log('worker', 'trace.completed', str(run_id))
    except Exception as exc:
        logging.exception('trace failed')
        with Session() as s:
            tr = s.get(Trace, run_id)
            tr.status = 'failed'
            tr.error = str(exc)[:1000]
            s.commit()


def run_branch_message(raw):
    try:
        payload = json.loads(raw)
        experiments.run_branch(int(payload['branch_id']))
    except Exception:
        logging.exception('experiment branch failed')


def main():
    ensure_schema()
    pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    while True:
        Path('/tmp/worker-heartbeat').touch()
        try:
            # 分支队列优先，空了再取单计划队列，两者都是阻塞短轮询
            item = r.blpop(['operator-experiments', 'operator-traces'], timeout=2)
            if not item:
                continue
            queue_name, raw = item[0].decode() if isinstance(item[0], bytes) else item[0], item[1]
            if queue_name == 'operator-experiments':
                pool.submit(run_branch_message, raw)
            else:
                pool.submit(run_trace, int(raw))
        except Exception:
            logging.exception('worker loop')
            time.sleep(2)


if __name__ == '__main__':
    main()
