"""Strict checks and descriptive agreement for exploratory machine labels."""
import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
ROW_KEYS = {'query_id', 'doc_id', 'label', 'annotator', 'annotator_type', 'experimental', 'round', 'note'}
INPUT_KEYS = {'query_id', 'query_vi', 'doc_id', 'title', 'abstract', 'abstract_missing'}
GRADES = (0, 1, 2, 'unjudged')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_lines(path):
    text = path.read_text(encoding='utf-8')
    if not text.strip():
        raise ValueError(f'Empty file: {path}')
    rows = []
    for line in text.splitlines():
        if not line.strip():
            raise ValueError(f'Blank line: {path}')
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f'Non-object row: {path}')
        rows.append(row)
    return rows


def validate(base):
    manifest = json.loads((base / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['split'] != 'dev' or manifest['experimental'] is not True or manifest['annotator_type'] != 'machine':
        raise ValueError('Wrong experiment/split')
    inputs = {}
    for name, sha in manifest['input_sha256'].items():
        path = base / name
        if digest(path) != sha:
            raise ValueError(f'Input hash mismatch: {name}')
        for r in load_lines(path):
            if set(r) != INPUT_KEYS or not isinstance(r['query_id'], str) or not r['query_id'].startswith('vn2:dev:'):
                raise ValueError('Input schema/leakage/split')
            if not all(isinstance(r[k], str) and r[k].strip() for k in ('query_vi', 'title', 'doc_id')):
                raise ValueError('Missing mandatory input text')
            if not isinstance(r['abstract'], str) or r['abstract_missing'] is not (not r['abstract'].strip()):
                raise ValueError('Abstract missingness mismatch')
            key = (r['query_id'], r['doc_id'])
            if key in inputs:
                raise ValueError('Duplicate input pair')
            inputs[key] = r
    if len(inputs) != manifest['pair_count'] or len({k[0] for k in inputs}) != manifest['query_count']:
        raise ValueError('Incomplete input coverage')
    if sum(r['abstract_missing'] for r in inputs.values()) != manifest['abstract_missing']:
        raise ValueError('Incorrect missing abstract count')
    for name, sha in manifest['protected_sha256'].items():
        if digest(ROOT / name) != sha:
            raise ValueError(f'Protected resource changed: {name}')
    raters = []
    for who in ('A', 'B'):
        output = {}
        for r in load_lines(base / f'vn2_labels_machine_{who}_dev.jsonl'):
            if set(r) != ROW_KEYS:
                raise ValueError('Output required fields/schema/leakage')
            if r['annotator'] != f'machine_{who}' or r['annotator_type'] != 'machine' or r['experimental'] is not True or r['round'] != 'independent':
                raise ValueError('Machine identity required')
            label = r['label']
            if not ((type(label) is int and label in (0, 1, 2)) or label == 'unjudged'):
                raise ValueError('Null/bool/out-of-bound label')
            if not isinstance(r['note'], str) or not r['note'].strip():
                raise ValueError('Missing judgment reason')
            key = (r['query_id'], r['doc_id'])
            if key not in inputs or key in output:
                raise ValueError('Unknown split/pair or duplicate output')
            if inputs[key]['abstract_missing'] and label != 'unjudged':
                raise ValueError('Title-only paper must be unjudged')
            output[key] = r
        if set(output) != set(inputs):
            raise ValueError(f'Machine {who} missing pairs')
        raters.append(output)
    return inputs, raters, manifest


def report(base):
    inputs, (a, b), manifest = validate(base)
    spec = importlib.util.spec_from_file_location('existing_agreement', ROOT / 'scripts/score_vn_agreement.py')
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    graded = [(a[k]['label'], b[k]['label']) for k in inputs if a[k]['label'] != 'unjudged' and b[k]['label'] != 'unjudged']
    matrix = {str(g): {str(h): 0 for h in GRADES} for g in GRADES}
    for k in inputs:
        matrix[str(a[k]['label'])][str(b[k]['label'])] += 1
    disagreements = [k for k in inputs if a[k]['label'] != b[k]['label']]
    distributions = {who: {str(g): sum(r['label'] == g for r in rows.values()) for g in GRADES} for who, rows in [('A', a), ('B', b)]}
    exact = sum(x == y for x, y in graded)
    summary = {'status': 'PASS_VALIDATION', 'experimental': True, 'annotator_type': 'machine',
               'pair_count': len(inputs), 'graded_pairs': len(graded), 'unjudged_either': len(inputs) - len(graded),
               'both_unjudged': sum(a[k]['label'] == b[k]['label'] == 'unjudged' for k in inputs),
               'exact_graded': exact, 'raw_agreement_graded': exact / len(graded) if graded else None,
               'linearly_weighted_kappa': scorer.weighted_kappa(graded) if graded else None,
               'all_label_matches': len(inputs) - len(disagreements), 'disagreement_count': len(disagreements),
               'distribution': distributions, 'confusion_including_unjudged': matrix,
               'per_query': [], 'human_comparison': manifest['human_comparison'],
               'limits': ['Two independent contexts, same requested model gpt-6.1-sol / high; not independent model families.',
                          'No human-v2 labels available; agreement is not accuracy.',
                          'Only provided title/abstract judged; dev only, no adjudication or retrieval evaluation.'],
               'output_sha256': {who: digest(base / f'vn2_labels_machine_{who}_dev.jsonl') for who in ('A', 'B')}}
    for qid in sorted({k[0] for k in inputs}):
        keys = [k for k in inputs if k[0] == qid]
        summary['per_query'].append({'query_id': qid, 'query_vi': inputs[keys[0]]['query_vi'], 'pairs': len(keys),
            'disagreements': sum(a[k]['label'] != b[k]['label'] for k in keys),
            'A': dict(Counter(str(a[k]['label']) for k in keys)), 'B': dict(Counter(str(b[k]['label']) for k in keys))})
    (base / 'agreement.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fields = ['query_id', 'query_vi', 'doc_id', 'title', 'abstract_missing', 'machine_A', 'machine_B', 'note_A', 'note_B']
    for filename, keys in [('all_pairs.csv', list(inputs)), ('disagreements.csv', disagreements)]:
        with (base / filename).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for k in keys:
                writer.writerow({**{x: inputs[k][x] for x in fields[:5]}, 'machine_A': a[k]['label'], 'machine_B': b[k]['label'],
                                 'note_A': a[k]['note'], 'note_B': b[k]['note']})
    md = ['# Thử chấm bằng hai agent — dev v2', '',
          'Kết quả máy thử nghiệm; không phải nhãn người hoặc kết quả SG-034.', '',
          f"Mỗi agent chấm {len(inputs)} cặp. Phân bố: A {distributions['A']}; B {distributions['B']}.",
          f"Cả hai có nhãn số: {len(graded)}; giống nhau {exact}; agreement {summary['raw_agreement_graded']}; kappa trọng số tuyến tính {summary['linearly_weighted_kappa']}.",
          f"Cặp có ít nhất một unjudged: {summary['unjudged_either']}; cả hai unjudged: {summary['both_unjudged']}. Tổng bất đồng mọi loại nhãn: {len(disagreements)}.", '',
          '## So với người', '', 'Chưa đo: nhãn người đã lưu thuộc v1, còn thử nghiệm này dùng v2. Không ghép hai bộ query hoặc báo độ đúng khi chưa có nhãn người cùng cặp.', '',
          '## Giới hạn', '', 'Hai context chấm độc lập dùng cùng model yêu cầu gpt-6.1-sol/high; có thể cùng mắc lỗi. Độ đồng thuận không chứng minh độ đúng. Chỉ đọc title/abstract, không chấm test, không phân xử.', '',
          '## Xem kết quả', '', '[File máy A](vn2_labels_machine_A_dev.jsonl), [file máy B](vn2_labels_machine_B_dev.jsonl), [toàn bộ cặp CSV](all_pairs.csv), [cặp bất đồng CSV](disagreements.csv), [số đếm JSON](agreement.json).', '',
          '## Theo query', '', '| Query | Số cặp | Bất đồng |', '|---|---:|---:|']
    md += [f"| {r['query_id']} | {r['pairs']} | {r['disagreements']} |" for r in summary['per_query']]
    (base / 'REPORT.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True))


def selftest():
    # Real CLI subprocesses on synthetic fixtures; never change project labels.
    with tempfile.TemporaryDirectory(prefix='machine-label-neg-', dir=ROOT / '.tmp') as tmp:
        base = Path(tmp)
        r = {'query_id': 'vn2:dev:001', 'query_vi': 'Câu hỏi thử', 'doc_id': 'synthetic:1',
             'title': 'Fixture', 'abstract': '', 'abstract_missing': True}
        inp = base / 'input.jsonl'
        inp.write_text(json.dumps(r) + '\n', encoding='utf-8')
        manifest = {'split': 'dev', 'experimental': True, 'annotator_type': 'machine', 'pair_count': 1,
                    'query_count': 1, 'abstract_missing': 1, 'protected_sha256': {}, 'input_sha256': {'input.jsonl': digest(inp)}}
        mp = base / 'manifest.json'
        mp.write_text(json.dumps(manifest), encoding='utf-8')
        row = {'query_id': r['query_id'], 'doc_id': r['doc_id'], 'label': 'unjudged', 'annotator': 'machine_A',
               'annotator_type': 'machine', 'experimental': True, 'round': 'independent', 'note': 'Thiếu abstract.'}
        pa = base / 'vn2_labels_machine_A_dev.jsonl'
        pb = base / 'vn2_labels_machine_B_dev.jsonl'
        pb.write_text(json.dumps({**row, 'annotator': 'machine_B'}) + '\n', encoding='utf-8')
        outcomes = []
        def cli(name, expected):
            p = subprocess.run([sys.executable, str(Path(__file__).resolve()), 'validate', '--base', str(base)], capture_output=True, text=True)
            if p.returncode != expected:
                raise AssertionError(f'{name}: expected {expected}, got {p.returncode}: {p.stderr}')
            outcomes.append({'case': name, 'exit_code': p.returncode})
        pa.write_text(json.dumps(row) + '\n', encoding='utf-8')
        cli('valid_title_only_unjudged', 0)
        for name, mutation in [('null', {'label': None}), ('bool', {'label': True}), ('out_of_bounds', {'label': 3}),
                               ('title_only_graded', {'label': 0}), ('test_split', {'query_id': 'vn2:test:001'}),
                               ('human_identity', {'annotator_type': 'human'}), ('leakage', {'score': 0.9}), ('empty_reason', {'note': ''})]:
            pa.write_text(json.dumps({**row, **mutation}) + '\n', encoding='utf-8')
            cli(name, 1)
        missing = dict(row)
        del missing['label']
        pa.write_text(json.dumps(missing) + '\n', encoding='utf-8')
        cli('missing_required_field', 1)
        pa.write_text(json.dumps(row) + '\n' + json.dumps(row) + '\n', encoding='utf-8')
        cli('duplicate_pair', 1)
        pa.write_text('{malformed}\n', encoding='utf-8')
        cli('malformed_json', 1)
        pa.unlink()
        cli('missing_label_file', 1)
        pa.write_text(json.dumps(row) + '\n', encoding='utf-8')
        for name, mutation in [('missing_title', {'title': ''}), ('missing_query_text', {'query_vi': ''}),
                               ('malformed_abstract', {'abstract': None}), ('input_test_split', {'query_id': 'vn2:test:001'}),
                               ('input_leakage', {'score': 0.5})]:
            inp.write_text(json.dumps({**r, **mutation}) + '\n', encoding='utf-8')
            manifest['input_sha256']['input.jsonl'] = digest(inp)
            mp.write_text(json.dumps(manifest), encoding='utf-8')
            cli(name, 1)
        inp.unlink()
        cli('missing_input_resource', 1)
        (BASE / 'negative_checks.json').write_text(json.dumps({'synthetic': True, 'status': 'PASS', 'cases': outcomes}, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': 'PASS', 'cases': len(outcomes), 'negative_cli_exit1': sum(o['exit_code'] == 1 for o in outcomes)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['validate', 'report', 'selftest'])
    parser.add_argument('--base', type=Path, default=BASE)
    args = parser.parse_args()
    try:
        if args.mode == 'selftest':
            selftest()
        elif args.mode == 'report':
            report(args.base)
        else:
            inputs, _, _ = validate(args.base)
            print(json.dumps({'status': 'PASS_VALIDATION', 'pairs_per_agent': len(inputs)}))
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
