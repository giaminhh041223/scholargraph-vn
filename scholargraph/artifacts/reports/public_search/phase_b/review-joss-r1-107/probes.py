import copy, hashlib, importlib.util, json, os, runpy, subprocess, sys, tempfile
from pathlib import Path
import httpx
from scholargraph.public_search import site_crawler as m

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(__file__).resolve().parent
SESSION = Path(tempfile.mkdtemp(prefix='probe-',dir=SCRATCH))
spec = importlib.util.spec_from_file_location('fixture_module', ROOT / 'tests/unit/test_public_site_crawler.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
results = []

def make(name, overrides=None):
    project, cfg_file, cfg = t.create_valid_test_env(SESSION/name)
    data = cfg.model_dump()
    if overrides:
        data.update(overrides)
        cfg = m.JossConfig.model_validate(data)
        cfg_file.write_text(json.dumps(data), encoding='utf-8')
    return project, cfg_file, cfg, project/cfg.data_root/'run'

def client(calls, robots=None, badpaper=False):
    def handler(req):
        calls.append(str(req.url))
        if req.url.path == m.ROBOTS_PATH:
            return httpx.Response(200, content=t.SAMPLE_ROBOTS if robots is None else robots, headers={'content-type':'text/plain'})
        if req.url.path == m.START_PATH:
            return httpx.Response(200, content=t.SAMPLE_LISTING_HTML, headers={'content-type':'text/html'})
        doi = req.url.path.removeprefix('/papers/')
        content = b'<html>title only</html>' if badpaper else t.SAMPLE_PAPER_HTML.replace('10.21105/joss.09260',doi).encode()
        return httpx.Response(200, content=content, headers={'content-type':'text/html'})
    return httpx.Client(transport=httpx.MockTransport(handler))

def run(project, cfg, folder, calls, resume=False, **kwargs):
    with client(calls, **kwargs) as c:
        with m.JossCrawler(project,cfg,folder,resume=resume,client=c,clock=lambda:1000.0,sleeper=lambda _:None,dns_resolver=t.fake_global_dns_resolver) as cr:
            return cr.crawl()

def record(name, **data):
    results.append({'probe':name,**data})

# Create genuine completed runs, then poison only the indicated artifact.
mutations = {
 'missing_counters':lambda cp:cp.pop('counters'),
 'negative_counter':lambda cp:cp['counters'].update(pages_fetched=-99),
 'missing_schema':lambda cp:cp.pop('schema_version'),
 'malformed_frontier':lambda cp:cp.update(frontier={'qrels':'poison'}),
 'missing_title':lambda cp:cp['records'][0].pop('title'),
 'mutated_title':lambda cp:cp['records'][0].update(title='INJECTED WITHOUT RAW CHANGE'),
 'leakage_record':lambda cp:cp['records'][0].update(test_labels=['SECRET'],score=100),
 'missing_visited':lambda cp:cp.update(visited=[]),
}
for name, mutate in mutations.items():
    project,cfg_file,cfg,folder=make(name)
    run(project,cfg,folder,[])
    path=folder/'checkpoint.json'
    cp=json.loads(path.read_text()); mutate(cp); path.write_text(json.dumps(cp),encoding='utf-8')
    calls=[]
    try:
        result=run(project,cfg,folder,calls,resume=True)
        record(name,status=result['status'],counters=result['counters'],first_record=result['records'][0],calls=calls)
    except Exception as e:
        record(name,error=type(e).__name__,message=str(e),calls=calls)

for name in ['records_json_missing','records_json_corrupt']:
    project,_,cfg,folder=make(name); run(project,cfg,folder,[])
    if name.endswith('missing'): (folder/'records.json').unlink()
    else: (folder/'records.json').write_text('POISON',encoding='utf-8')
    record(name,status=run(project,cfg,folder,[],resume=True)['status'])

project,_,cfg,folder=make('parse_failure_resume',{'max_pages':2})
calls=[]
try: run(project,cfg,folder,calls,badpaper=True)
except Exception as e: record('parse_failure_first',error=type(e).__name__,checkpoint=json.loads((folder/'checkpoint.json').read_text()),calls=calls)
calls=[]; result=run(project,cfg,folder,calls,resume=True)
record('parse_failure_resume',status=result['status'],records_count=result['records_count'],counters=result['counters'],calls=calls)

project,_,cfg,folder=make('listing_drift')
def drift(req):
    return httpx.Response(200,content=t.SAMPLE_ROBOTS if req.url.path==m.ROBOTS_PATH else b'<html>broken listing</html>',headers={'content-type':'text/plain' if req.url.path==m.ROBOTS_PATH else 'text/html'})
with httpx.Client(transport=httpx.MockTransport(drift)) as c:
    try:
        with m.JossCrawler(project,cfg,folder,client=c,sleeper=lambda _:None,dns_resolver=t.fake_global_dns_resolver) as cr: cr.crawl()
    except Exception as e: record('listing_drift_first',error=type(e).__name__)
result=run(project,cfg,folder,[],resume=True)
record('listing_drift_resume',status=result['status'],records_count=result['records_count'],counters=result['counters'])

for name,robots in [('malformed_robots',b'<html>not a robots file</html>'),('crawl_delay',b'User-agent: *\nDisallow:\nCrawl-delay: 10\n')]:
    project,_,cfg,folder=make(name); calls=[]
    try: record(name,status=run(project,cfg,folder,calls,robots=robots)['status'],calls=calls)
    except Exception as e: record(name,error=type(e).__name__)

project,_,cfg,folder=make('protected_root',{'data_root':'data/benchmarks'})
with m.JossCrawler(project,cfg,folder) as cr: record('protected_root',created=folder.exists(),run_dir=str(folder))
project,_,cfg,folder=make('absolute_drive_root',{'data_root':str(SESSION/'external').replace('\\','/')})
with m.JossCrawler(project,cfg,folder) as cr: record('absolute_drive_root',created=folder.exists(),run_dir=str(folder))

record('empty_dns',accepted=m.validate_url_and_dns(m.CANONICAL_ORIGIN+m.START_PATH,cfg,dns_resolver=lambda _:[]) is None)

env=os.environ.copy(); env['PYTHONPATH']=str(ROOT/'src'); env['PYTHONDONTWRITEBYTECODE']='1'
p=subprocess.run([sys.executable,str(ROOT/'scripts/crawl_public.py'),'--config','MISSING','--run-dir',str(SCRATCH/'unused')],cwd=ROOT,env=env,capture_output=True,text=True)
record('cli_missing_config',exit_code=p.returncode,stderr=p.stderr)
env.pop('PYTHONPATH')
p=subprocess.run([sys.executable,str(ROOT/'scripts/crawl_public.py'),'--help'],cwd=ROOT,env=env,capture_output=True,text=True)
record('cli_clean_env_help',exit_code=p.returncode,stderr=p.stderr,stdout=p.stdout)

# True subprocess executes original script __main__; replace only network dependency.
env['PYTHONPATH']=str(ROOT/'src')
project,cfg_file,cfg,folder=make('cli_checkpoint_poison'); run(project,cfg,folder,[])
cp=json.loads((folder/'checkpoint.json').read_text()); cp['records'][0]['test_labels']=['SECRET']; cp.pop('counters'); (folder/'checkpoint.json').write_text(json.dumps(cp))
code="""import httpx,runpy,sys
from scholargraph.public_search import site_crawler as m
Original=m.JossCrawler
class Offline(Original):
 def __init__(self,**kw):
  super().__init__(**kw,client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'User-agent: *\\nDisallow:\\n',headers={'content-type':'text/plain'}))),dns_resolver=lambda _:['93.184.216.34'],sleeper=lambda _:None)
m.JossCrawler=Offline
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
"""
p=subprocess.run([sys.executable,'-c',code,str(ROOT/'scripts/crawl_public.py'),'--project-root',str(project),'--config',str(cfg_file),'--run-dir',str(folder),'--resume'],cwd=ROOT,env=env,capture_output=True,text=True)
record('cli_poison_checkpoint',exit_code=p.returncode,stderr=p.stderr,stdout=p.stdout)

manifest=json.loads((ROOT/'data/public_search/phase_b/policy-107/manifest.json').read_text())
item=next(x for x in manifest['resources'] if x['url'].endswith('joss.09260'))
rec=m.JossPaperParser().parse_record((ROOT/item['raw_path']).read_bytes(),item['url'],m.PARSER_VERSION,item['retrieved_at'])
record('policy_example',record=rec.model_dump(mode='json'))

(SCRATCH/'probe-result.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
for x in results:
    print(x['probe'], json.dumps({k:v for k,v in x.items() if k not in ('first_record','checkpoint','stdout','stderr','record','calls')},ensure_ascii=False))
