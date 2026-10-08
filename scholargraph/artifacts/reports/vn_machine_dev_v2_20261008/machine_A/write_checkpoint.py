import json,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent
rows=[json.loads(s) for s in (root/'input'/sys.argv[1]).read_text(encoding='utf-8').splitlines()]
decisions=json.load(sys.stdin)
assert len(rows)==len(decisions),(len(rows),len(decisions))
output=[]
for r,(label,note) in zip(rows,decisions):
 assert label in (0,1,2,'unjudged') and note.strip()
 assert not (r['abstract_missing'] or not r['abstract'].strip()) or label=='unjudged'
 output.append(dict(query_id=r['query_id'],doc_id=r['doc_id'],label=label,annotator='machine_A',annotator_type='machine',experimental=True,round='independent',note=note))
assert len({(r['query_id'],r['doc_id']) for r in output})==len(output)
path=root/'machine_A'/sys.argv[1]
assert not path.exists(),path
path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in output),encoding='utf-8')
print(path.name,len(output))
