import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    number = sys.argv[1]
    rows = [json.loads(s) for s in (ROOT / 'input' / f'vn2_dev_{number}.jsonl').read_text(encoding='utf-8').splitlines()]
    choices = (ROOT / 'machine_B' / f'decisions_{number}.tsv').read_text(encoding='utf-8').splitlines()
    if len(rows) != len(choices):
        raise ValueError(f'Row count mismatch: {len(rows)} != {len(choices)}')
    out = []
    for row, choice in zip(rows, choices):
        label, note = choice.split('|', 1)
        if label not in ('0', '1', '2', 'unjudged') or not note.strip():
            raise ValueError('Invalid manual decision')
        if row['abstract_missing'] or not row['abstract'].strip():
            if label != 'unjudged':
                raise ValueError('Missing abstract must be unjudged')
        out.append(dict(query_id=row['query_id'], doc_id=row['doc_id'], label=label if label == 'unjudged' else int(label), annotator='machine_B', annotator_type='machine', experimental=True, round='independent', note=note))
    if len({(r['query_id'], r['doc_id']) for r in out}) != len(out):
        raise ValueError('Duplicate pairs')
    (ROOT / 'machine_B' / f'vn2_labels_machine_B_{number}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out), encoding='utf-8')
    print(f'{number}: saved {len(out)} independently judged pairs')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
