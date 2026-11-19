from src.services import datasets,plans,traces,experiments
from src.services.audit import log
def save_dataset(data,user,item_id=None):
 row=datasets.save(data,item_id);log(user.email,'dataset.save',row['name']);return row
def save_plan(data,user,item_id=None):
 row=plans.save(data,item_id);log(user.email,'plan.save',f"{row['name']}@v{row['version']}");return row
def start_trace(data,user):
 row=traces.create(data);log(user.email,'trace.queue',row['name']);return row
def start_experiment(data,user):
 row=experiments.create(data);log(user.email,'experiment.start',row['name']);return row
def retry_experiment(item_id,user):
 row=experiments.retry(item_id);log(user.email,'experiment.retry',row['name']);return row
