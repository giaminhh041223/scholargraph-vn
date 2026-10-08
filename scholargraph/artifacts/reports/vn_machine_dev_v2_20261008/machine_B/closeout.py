import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from validate import read, validate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT = ROOT / 'vn2_labels_machine_B_dev.jsonl'

def dump(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')

rows = []
for n in range(1, 11):
    rows.extend(read(HERE / f'vn2_labels_machine_B_{n:03d}.jsonl'))
dump(OUTPUT, rows)
summary = validate(ROOT / 'input', OUTPUT)
cases = ['missing_file', 'malformed_json', 'title_missing', 'text_only', 'abstract_missing_field', 'abstract_wrong_type', 'score_out_of_range', 'title_only_judged', 'missing_note', 'duplicate_pair', 'unexpected_test_split', 'human_annotator', 'missing_pair']
checks = []
for case in cases:
    with tempfile.TemporaryDirectory(prefix='adversarial_', dir=HERE) as tmp:
        tmpdir = Path(tmp)
        inputs = tmpdir / 'input'
        shutil.copytree(ROOT / 'input', inputs)
        target = tmpdir / 'labels.jsonl'
        candidate_rows = read(OUTPUT)
        source = inputs / 'vn2_dev_001.jsonl'
        source_rows = read(source)
        if case == 'missing_file':
            source.unlink()
        elif case == 'malformed_json':
            source.write_text('{invalid json}\n', encoding='utf-8')
        elif case == 'title_missing':
            del source_rows[0]['title']
            dump(source, source_rows)
        elif case == 'text_only':
            source_rows[0]['title'] = ''
            dump(source, source_rows)
        elif case == 'abstract_missing_field':
            del source_rows[0]['abstract']
            dump(source, source_rows)
        elif case == 'abstract_wrong_type':
            source_rows[0]['abstract'] = 12
            dump(source, source_rows)
        elif case == 'score_out_of_range':
            candidate_rows[0]['label'] = 3
        elif case == 'title_only_judged':
            row = next(r for r in candidate_rows if r['label'] == 'unjudged')
            row['label'] = 0
        elif case == 'missing_note':
            candidate_rows[0]['note'] = ''
        elif case == 'duplicate_pair':
            candidate_rows.append(candidate_rows[0])
        elif case == 'unexpected_test_split':
            candidate_rows[0]['query_id'] = 'vn2:test:001'
        elif case == 'human_annotator':
            candidate_rows[0]['annotator_type'] = 'human'
        elif case == 'missing_pair':
            candidate_rows.pop()
        dump(target, candidate_rows)
        result = subprocess.run([sys.executable, '-X', 'utf8', str(HERE / 'validate.py'), str(inputs), str(target)], capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 1 or 'FAIL:' not in result.stderr:
            raise RuntimeError(f'Negative case did not fail clearly: {case}')
        checks.append(dict(case=case, exit_code=result.returncode, passed=True, error=result.stderr.strip()))
summary['negative_tests'] = checks
summary['scope'] = 'Only supplied title/abstract/query_vi; independent machine experiment; not human SG-033 or correctness evaluation.'
(HERE / 'validation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(summary, ensure_ascii=False, indent=2))
