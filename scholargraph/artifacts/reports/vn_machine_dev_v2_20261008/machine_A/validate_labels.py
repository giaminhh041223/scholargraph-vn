import json,sys
from pathlib import Path
FIELDS={'query_id','doc_id','label','annotator','annotator_type','experimental','round','note'}
def require(ok,message):
 if not ok: raise ValueError(message)
def read(path):
 require(path.is_file(),'missing required file: '+str(path))
 return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
def validate(input_dir,labels):
 expected={}
 for k in range(1,11):
  for x in read(input_dir/f'vn2_dev_{k:03d}.jsonl'):
   require(x['query_id']==f'vn2:dev:{k:03d}','input split leakage or wrong query')
   require(isinstance(x['title'],str) and bool(x['title'].strip()),'missing title')
   require(isinstance(x['abstract'],str),'invalid abstract')
   require(type(x['abstract_missing']) is bool,'invalid missing flag')
   require(x['abstract_missing']==(not bool(x['abstract'].strip())),'inconsistent missing flag')
   require(not {'label','qrel','qrels'}.intersection(x),'label leakage in input')
   pair=(x['query_id'],x['doc_id'])
   require(pair not in expected,'duplicate input pair')
   expected[pair]=x
 require(len(expected)==227,'input coverage must be 227')
 seen=set()
 rows=read(labels)
 for y in rows:
  require(set(y)==FIELDS,'wrong output schema')
  pair=(y['query_id'],y['doc_id'])
  require(pair in expected,'unknown or leaked split pair')
  require(pair not in seen,'duplicate output pair')
  seen.add(pair)
  require(y['annotator']=='machine_A' and y['annotator_type']=='machine','wrong annotator')
  require(y['experimental'] is True and y['round']=='independent','wrong experiment fields')
  require((type(y['label']) is int and y['label'] in (0,1,2)) or y['label']=='unjudged','invalid label')
  require(isinstance(y['note'],str) and bool(y['note'].strip()),'missing note')
  require(not expected[pair]['abstract_missing'] or y['label']=='unjudged','title-only requires unjudged')
 require(seen==set(expected),'missing required output pairs')
 return len(rows)
if __name__=='__main__':
 try:
  require(len(sys.argv)==3,'usage: validate_labels.py INPUT_DIR LABELS_JSONL')
  print('PASS_SCHEMA_COVERAGE_ONLY',validate(Path(sys.argv[1]),Path(sys.argv[2])))
 except Exception as e:
  print('FAIL:',str(e),file=sys.stderr)
  sys.exit(1)
