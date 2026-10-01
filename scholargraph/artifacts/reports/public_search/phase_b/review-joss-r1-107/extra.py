import importlib.util,json,tempfile
from pathlib import Path
import httpx
from scholargraph.public_search import site_crawler as m
root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fixture',root/'tests/unit/test_public_site_crawler.py'); t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
out=[]
for name,html in [
 ('foreign_abstract_url',t.SAMPLE_PAPER_HTML.replace('</head>','<meta name="citation_abstract_html_url" content="https://foreign.org/qrels"> </head>')),
 ('pdf_credentials_port',t.SAMPLE_PAPER_HTML.replace('https://joss.theoj.org/papers/10.21105/joss.09260.pdf','https://user:pass@joss.theoj.org:8080/papers/10.21105/joss.09260.pdf'))]:
 try:
  rec=m.JossPaperParser().parse_record(html.encode(),m.CANONICAL_ORIGIN+'/papers/10.21105/joss.09260',m.PARSER_VERSION,'INVALID_TIME')
  out.append({'probe':name,'accepted':True,'retrieved_at':rec.retrieved_at,'pdf_url':rec.pdf_url})
 except Exception as e: out.append({'probe':name,'error':type(e).__name__})
project,cfg_file,cfg=t.create_valid_test_env(Path(tempfile.mkdtemp(prefix='extra-',dir=root/'.tmp/jr107')))
times=[]; now=[1000.0]
def sleep(seconds): now[0]+=seconds
def handler(req):
 times.append(now[0]); url=str(req.url)
 if req.url.path==m.ROBOTS_PATH: body=b'User-agent: *\nDisallow:\nCrawl-delay: 10\n'; ct='text/plain'
 elif req.url.path==m.START_PATH: body=t.SAMPLE_LISTING_HTML.encode(); ct='text/htmlgarbage'
 else: body=t.SAMPLE_PAPER_HTML.replace('10.21105/joss.09260',req.url.path.removeprefix('/papers/')).encode(); ct='text/html'
 return httpx.Response(200,content=body,headers={'content-type':ct})
with httpx.Client(transport=httpx.MockTransport(handler)) as c:
 with m.JossCrawler(project,cfg,project/cfg.data_root/'run',client=c,clock=lambda:now[0],sleeper=sleep,dns_resolver=lambda _:['93.184.216.34']) as cr:
  result=cr.crawl()
out.append({'probe':'crawl_delay_and_malformed_media_type','status':result['status'],'times':times,'intervals':[b-a for a,b in zip(times,times[1:])]})
(root/'.tmp/jr107/extra-result.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
