"""Real independent SQLite stores, actual artifact log/download and paginated searches."""
import math
import pytest
import mlflow
from mlflow import MlflowClient
from mlflow.tracking import fluent

def setup(tmp_path,extension,separate):
 global_uri='sqlite:///'+(tmp_path/'global.db').as_posix()
 client_uri='sqlite:///'+(tmp_path/'client.db').as_posix() if separate else global_uri
 mlflow.set_tracking_uri(global_uri)
 global_client=MlflowClient(tracking_uri=global_uri)
 global_client.create_experiment('decoy',artifact_location=(tmp_path/'decoy').as_uri())
 client=MlflowClient(tracking_uri=client_uri)
 eid=client.create_experiment('target',artifact_location=(tmp_path/'artifacts').as_uri())
 ids=[]
 for i in range(5):
  rid=client.create_run(eid).info.run_id;ids.append(rid)
  client.log_param(rid,'category','row-'+str(i))
  if i%2==0:client.log_metric(rid,'score',float(i))
  client.set_tag(rid,'label','tag-'+str(i))
  client.log_table(rid,{'value':[i],'run_id':['artifact-'+str(i)]},'nested/table.'+extension)
  client.set_terminated(rid)
 return client,eid,ids,global_uri

@pytest.mark.parametrize('extension',['json','parquet'])
@pytest.mark.parametrize('subset',[False,True])
def test_client_backend_pages_and_metadata(tmp_path,monkeypatch,extension,subset):
 client,eid,ids,global_uri=setup(tmp_path,extension,True)
 monkeypatch.setattr(fluent,'NUM_RUNS_PER_PAGE_PANDAS',2)
 calls=[];real=client.search_runs
 def observe(*args,**kwargs):
  result=real(*args,**kwargs)
  calls.append({'requested':kwargs.get('max_results'),'token':kwargs.get('page_token'),'run_ids':[r.info.run_id for r in result]})
  return result
 monkeypatch.setattr(client,'search_runs',observe)
 selected=[ids[0],ids[2],ids[4]] if subset else ids
 result=client.load_table(eid,'nested/table.'+extension,run_ids=selected if subset else None,
  extra_columns=['run_id','params.category','metrics.score','tags.label']).sort_values('value').reset_index(drop=True)
 values=[0,2,4] if subset else list(range(5))
 assert result['value'].tolist()==values
 assert result['run_id'].tolist()==['artifact-'+str(i) for i in values]
 assert result['run_id_'].tolist()==selected
 assert result['params.category'].tolist()==['row-'+str(i) for i in values]
 assert result['tags.label'].tolist()==['tag-'+str(i) for i in values]
 for i,value in zip(values,result['metrics.score']):assert value==float(i) if i%2==0 else math.isnan(value)
 assert len(calls)==(2 if subset else 3)
 assert calls[0]['token'] is None and all(x['token'] for x in calls[1:])
 assert all(x['requested']==2 for x in calls)
 assert {r for x in calls for r in x['run_ids']}==set(selected)
 assert mlflow.get_tracking_uri()==global_uri

@pytest.mark.parametrize('extension',['json','parquet'])
def test_global_client_control(tmp_path,extension):
 client,eid,ids,global_uri=setup(tmp_path,extension,False)
 result=client.load_table(eid,'nested/table.'+extension,run_ids=[ids[1]])
 assert result.to_dict('list')=={'value':[1],'run_id':['artifact-1']}
 assert mlflow.get_tracking_uri()==global_uri
