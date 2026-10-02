import copy,hashlib,importlib.util,json,os,runpy,subprocess,sys,tempfile
from pathlib import Path
import httpx
from scholargraph.public_search import site_crawler as m
ROOT=Path(__file__).resolve().parents[2]; SCRATCH=Path(__file__).parent; SESSION=Path(tempfile.mkdtemp(prefix='probe-',dir=SCRATCH))
spec=importlib.util.spec_from_file_location('fixture',ROOT/'tests/unit/test_public_site_crawler.py'); t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
out=[]
def emit(name,**kw): out.append({'probe':name,**kw})
def make(name,overrides=None):
 p,cf,c=t.create_valid_test_env(SESSION/name)
 if overrides:
  d=c.model_dump(); d.update(overrides); c=m.JossConfig.model_validate(d); cf.write_text(json.dumps(d))
 return p,cf,c,p/c.data_root/'run'
def run(p,c,f,calls,resume=False,badpaper=False,robots=None,dns=None):
 def handler(req):
  calls.append(str(req.url))
  if req.url.path==m.ROBOTS_PATH: b=t.SAMPLE_ROBOTS if robots is None else robots; ct='text/plain'
  elif req.url.path==m.START_PATH: b=t.SAMPLE_LISTING_HTML.encode(); ct='text/html'
  else: b=b'<html>title only</html>' if badpaper else t.SAMPLE_PAPER_HTML.replace('10.21105/joss.09260',req.url.path.removeprefix('/papers/')).encode(); ct='text/html'
  return httpx.Response(200,content=b,headers={'content-type':ct})
 with httpx.Client(transport=httpx.MockTransport(handler)) as cl:
  with m.JossCrawler(p,c,f,resume=resume,client=cl,sleeper=lambda _:None,dns_resolver=dns or t.fake_global_dns_resolver) as cr: return cr.crawl()
mutations={
 'missing_counters':lambda cp:cp.pop('counters'),
 'altered_title':lambda cp:cp['records'][0].update(title='INJECTED'),
 'leakage':lambda cp:cp['records'][0].update(test_labels=['SECRET']),
 'wrong_schema':lambda cp:cp.update(schema_version=42,created_at='INVALID',updated_at='INVALID'),
 'provenance_poison':lambda cp:cp['records'][0]['provenance'].update(landing_url='https://foreign.org/qrels',raw_sha256='0'*64,parser_version='evil',meta_fields=['test_labels']),
 'visited_poison':lambda cp:cp['visited'][1].update(url='https://foreign.org/paper',config_hash='0'*64,retrieved_at='INVALID',parser_version='evil'),
 'frontier_poison':lambda cp:cp.update(frontier=['https://foreign.org/paper']),
 'links_count_poison':lambda cp:cp['counters'].update(links_found=0,duplicate_links=100),
}
for name,mutate in mutations.items():
 p,cf,c,f=make(name); run(p,c,f,[]); cp=json.loads((f/'checkpoint.json').read_text()); mutate(cp); (f/'checkpoint.json').write_text(json.dumps(cp)); (f/'records.json').write_text(json.dumps(cp['records']))
 calls=[]
 try: r=run(p,c,f,calls,resume=True); emit(name,status=r['status'],counters=r['counters'],calls=calls)
 except Exception as e: emit(name,error=type(e).__name__,calls=calls)
p,cf,c,f=make('duplicate_records'); run(p,c,f,[]); cp=json.loads((f/'checkpoint.json').read_text()); cp['records'].append(copy.deepcopy(cp['records'][0])); cp['visited'].append(copy.deepcopy(cp['visited'][1])); cp['counters'].update(pages_fetched=5,papers_parsed=4,unique_papers=4); (f/'checkpoint.json').write_text(json.dumps(cp)); (f/'records.json').write_text(json.dumps(cp['records']))
try: r=run(p,c,f,[],resume=True); emit('duplicate_records',status=r['status'],counters=r['counters'],record_ids=[x['id'] for x in r['records']])
except Exception as e: emit('duplicate_records',error=type(e).__name__)
for maxpages in [2,5]:
 p,cf,c,f=make('malformed_'+str(maxpages),{'max_pages':maxpages}); calls=[]
 try: run(p,c,f,calls,badpaper=True)
 except Exception as e: emit('malformed_first_'+str(maxpages),error=type(e).__name__,checkpoint=json.loads((f/'checkpoint.json').read_text()))
 calls=[]
 try: r=run(p,c,f,calls,resume=True,badpaper=True); emit('malformed_resume_'+str(maxpages),status=r['status'],records_count=r['records_count'],counters=r['counters'],calls=calls)
 except Exception as e: emit('malformed_resume_'+str(maxpages),error=type(e).__name__,calls=calls)
# Failure on first malformed robots must leave failed checkpoint for resume.
p,cf,c,f=make('malformed_robots')
try: run(p,c,f,[],robots=b'<html>garbage</html>')
except Exception as e: emit('malformed_robots',error=type(e).__name__,checkpoint_exists=(f/'checkpoint.json').exists())
p,cf,c,f=make('private_dns'); calls=[]
try: run(p,c,f,calls,dns=lambda _:['127.0.0.1'])
except Exception as e: emit('private_dns',error=type(e).__name__,actual_http_calls=len(calls),checkpoint=json.loads((f/'checkpoint.json').read_text()))
# Windows junction of canonical base should not define a permitted root outside project.
p,cf,c,f=make('junction'); target=SESSION/'junction_target'; target.mkdir(); base=p/c.data_root
cmd="New-Item -ItemType Junction -Path '"+str(base)+"' -Target '"+str(target)+"' | Out-Null"
proc=subprocess.run(['powershell','-NoProfile','-Command',cmd],capture_output=True,text=True)
if proc.returncode: emit('junction',setup_error=proc.stderr)
else:
 try:
  with m.JossCrawler(p,c,f) as cr: emit('junction',accepted=True,base_is_symlink=base.is_symlink(),base_is_junction=base.is_junction() if hasattr(base,'is_junction') else 'API absent',resolved_run=str(cr.run_dir),outside_project=not cr.run_dir.is_relative_to(p.resolve()))
 except Exception as e: emit('junction',error=type(e).__name__,message=str(e))
# CLI negative corruption and malformed-at-budget resume in a real subprocess.
env=os.environ.copy(); env['PYTHONPATH']=str(ROOT/'src'); env['PYTHONDONTWRITEBYTECODE']='1'
code="""import httpx,runpy,sys
from scholargraph.public_search import site_crawler as m
O=m.JossCrawler
class Offline(O):
 def __init__(self,**kw):
  super().__init__(**kw,client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'User-agent: *\\nDisallow:\\n',headers={'content-type':'text/plain'}))),dns_resolver=lambda _:['93.184.216.34'],sleeper=lambda _:None)
m.JossCrawler=Offline
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
"""
for name in ['cli_missing_counters','cli_malformed_at_budget']:
 p,cf,c,f=make(name,{'max_pages':2} if 'malformed' in name else None)
 try: run(p,c,f,[],badpaper='malformed' in name)
 except m.ParseError: pass
 if 'missing' in name:
  cp=json.loads((f/'checkpoint.json').read_text()); cp.pop('counters'); (f/'checkpoint.json').write_text(json.dumps(cp))
 proc=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts/crawl_public.py'),'--project-root',str(p),'--config',str(cf),'--run-dir',str(f),'--resume'],cwd=ROOT,env=env,capture_output=True,text=True)
 emit(name,exit_code=proc.returncode,stdout=proc.stdout,stderr=proc.stderr)
env.pop('PYTHONPATH')
for args in [['--help'],['--config','MISSING','--run-dir',str(SESSION/'unused')]]:
 proc=subprocess.run([sys.executable,str(ROOT/'scripts/crawl_public.py'),*args],cwd=ROOT,env=env,capture_output=True,text=True)
 emit('cli_clean_'+args[0],exit_code=proc.returncode,stderr=proc.stderr)
(SCRATCH/'results.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
for x in out: print(json.dumps({k:v for k,v in x.items() if k not in ('checkpoint','stdout','stderr')},ensure_ascii=False))
