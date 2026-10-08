import json
import sys
from collections import Counter
from pathlib import Path

FIELDS = {'query_id', 'doc_id', 'label', 'annotator', 'annotator_type', 'experimental', 'round', 'note'}

def read(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]

def validate(input_dir, label_path):
    sources = {}
    for n in range(1, 11):
        qid = f'vn2:dev:{n:03d}'
        path = input_dir / f'vn2_dev_{n:03d}.jsonl'
        rows = read(path)
        if not rows:
            raise ValueError(f'Empty query file: {path.name}')
        for row in rows:
            if row['query_id'] != qid:
                raise ValueError('Unexpected split/query ID')
            if not isinstance(row['query_vi'], str) or not row['query_vi'].strip():
                raise ValueError('Missing query')
            if not isinstance(row['title'], str) or not row['title'].strip():
                raise ValueError('Missing title')
            if not isinstance(row['abstract'], str) or type(row['abstract_missing']) is not bool:
                raise ValueError('Malformed abstract/missing flag')
            if row['abstract_missing'] != (not bool(row['abstract'].strip())):
                raise ValueError('Inconsistent abstract missing flag')
            if not isinstance(row['doc_id'], str) or not row['doc_id'].strip():
                raise ValueError('Missing document ID')
            key = (row['query_id'], row['doc_id'])
            if key in sources:
                raise ValueError('Duplicate source pair')
            sources[key] = row
    if len(sources) != 227:
        raise ValueError('Expected exactly 227 source pairs')
    missing_count = sum(row['abstract_missing'] for row in sources.values())
    if missing_count != 22:
        raise ValueError('Expected exactly 22 missing abstracts')
    labels = read(label_path)
    seen = set()
    for row in labels:
        if set(row) != FIELDS:
            raise ValueError('Output fields differ from rubric')
        key = (row['query_id'], row['doc_id'])
        if key in seen or key not in sources:
            raise ValueError('Duplicate or unexpected output pair/split')
        seen.add(key)
        label = row['label']
        if not ((type(label) is int and label in (0, 1, 2)) or label == 'unjudged'):
            raise ValueError('Invalid label')
        if row['annotator'] != 'machine_B' or row['annotator_type'] != 'machine' or row['experimental'] is not True or row['round'] != 'independent':
            raise ValueError('Invalid experimental annotator metadata')
        if not isinstance(row['note'], str) or not row['note'].strip():
            raise ValueError('Missing judgment rationale')
        if sources[key]['abstract_missing'] and label != 'unjudged':
            raise ValueError('Title-only pair has judged label')
    if seen != set(sources):
        raise ValueError('Output coverage differs from input')
    return dict(pairs=len(labels), queries=len({r['query_id'] for r in labels}), missing_abstracts=missing_count, labels=dict(Counter(str(r['label']) for r in labels)), coverage_exact=True, duplicate_pairs=0)

if __name__ == '__main__':
    try:
        print(json.dumps(validate(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False))
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
