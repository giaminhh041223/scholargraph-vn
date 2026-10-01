import copy,json
from pathlib import Path
from scholargraph.public_search.contracts import SearchEnvelope
p=Path(r"D:/Web_mining_20261/scholargraph/.worktrees/public-gemini/scholargraph/tests/fixtures/public_search/gemini/ux_examples.json")
g=json.loads(p.read_text())['examples']['example_03_tt02_success_plus_empty_with_hit']['envelope']
for name,mut in [('missing_source_total',lambda e:e['snapshot']['source_results'][0].pop('source_total',None)),('missing_truncated',lambda e:e['snapshot']['source_results'][0].pop('truncated',None)),('source_total_string',lambda e:e['snapshot']['source_results'][0].__setitem__('source_total','wrong')),('truncated_string',lambda e:e['snapshot']['source_results'][0].__setitem__('truncated','wrong')),('calendar_year0000',lambda e:e['snapshot'].__setitem__('fetched_at','0000-01-01T00:00:00Z')),('calendar_offset+23:59',lambda e:e['snapshot'].__setitem__('fetched_at','2026-01-01T00:00:00+23:59'))]:
 e=copy.deepcopy(g); mut(e)
 try: SearchEnvelope.model_validate(e); print('[FAIL]',name,'accepted')
 except Exception as ex: print('[PASS]',name,'reject',str(ex).splitlines()[0])
