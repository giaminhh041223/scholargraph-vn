"""Create a dev-only blinded packet from the exact human labeling kit."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
kit = ROOT / 'artifacts/vn_labeling_kit_SG033_v2/label_tool.html'
html = kit.read_text(encoding='utf-8')
matches = re.findall(r'<script id="poolDataScript" type="application/json">(.*?)</script>', html, re.S)
if len(matches) != 1:
    raise ValueError('Required unique blinded kit payload missing')
kit_doc = json.loads(matches[0])
pool_path = ROOT / 'data/annotations/v2/vn_pool.json'
pool = json.loads(pool_path.read_text(encoding='utf-8'))
if kit_doc['blinded'] is not True or pool['blinded'] is not True:
    raise ValueError('Unblinded input')
dev = [q for q in kit_doc['pools'] if q['split'] == 'dev']
expected = {(q['query_id'], c['doc_id']) for q in pool['pools'] if q['split'] == 'dev' for c in q['candidates']}
actual = [(q['query_id'], c['doc_id']) for q in dev for c in q['candidates']]
if len(dev) != 10 or len(actual) != 227 or len(set(actual)) != len(actual) or set(actual) != expected:
    raise ValueError('Dev kit/pool coverage mismatch')
input_dir = OUT / 'input'
input_dir.mkdir(exist_ok=False)
files = {}
for q in dev:
    if not q['query_id'].startswith('vn2:dev:') or not q['text_vi'].strip():
        raise ValueError('Wrong split/namespace or missing query text')
    rows = []
    for c in q['candidates']:
        if set(c) != {'position', 'doc_id', 'title', 'abstract', 'year'}:
            raise ValueError('Unexpected/leaking candidate field')
        if not isinstance(c['title'], str) or not c['title'].strip() or not isinstance(c['abstract'], str):
            raise ValueError('Missing title or malformed abstract')
        rows.append({'query_id': q['query_id'], 'query_vi': q['text_vi'], 'doc_id': c['doc_id'],
                     'title': c['title'], 'abstract': c['abstract'], 'abstract_missing': not c['abstract'].strip()})
    path = input_dir / (q['query_id'].replace(':', '_') + '.jsonl')
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    files[str(path.relative_to(OUT)).replace('\\', '/')] = hashlib.sha256(path.read_bytes()).hexdigest()
protected = ['data/annotations/v2/vn_labels.jsonl', 'data/annotations/v2/vn_pool.json',
             'data/annotations/v2/vn_query_manifest.json', 'data/annotations/vn_labels.jsonl',
             'data/annotations/v1_dev_labels_raw/vn_labels_A_dev.jsonl',
             'data/annotations/v1_dev_labels_raw/vn_labels_B_dev.jsonl', 'configs/frozen_main.json']
pins = {}
for name in protected:
    path = ROOT / name
    if not path.is_file():
        raise FileNotFoundError(name)
    pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest = {'schema_version': 1, 'experiment': 'machine_dev_v2', 'annotator_type': 'machine',
            'experimental': True, 'split': 'dev', 'pair_count': len(actual), 'query_count': len(dev),
            'abstract_missing': sum(not c['abstract'].strip() for q in dev for c in q['candidates']),
            'input_sha256': files, 'protected_sha256': pins,
            'kit_sha256': hashlib.sha256(kit.read_bytes()).hexdigest(),
            'human_comparison': 'NOT_MEASURED: available human exports are v1, not the v2 dev pairs',
            'use': 'exploratory only; not human labels, adjudication, freeze, tuning or test evaluation'}
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(OUT / 'RUBRIC.md').write_text('''# Chấm độc lập bằng máy — dev v2

Chỉ đọc 10 file input/vn2_dev_*.jsonl (227 cặp). Query tiếng Việt là nhu cầu tin chuẩn; không dùng bản dịch máy, tìm kiếm web, nhãn người, qrels, test, provenance hệ thống hoặc kết quả agent còn lại.

- 0: không trả lời bất kỳ phần nào; chỉ trùng từ khóa bề mặt.
- 1: trả lời một khía cạnh, hoặc cùng chủ đề nhưng khác khía cạnh/quy mô.
- 2: trả lời trực tiếp toàn bộ nhu cầu tin với thiết kế/kết quả phù hợp.
- unjudged: thiếu nội dung để kết luận; abstract rỗng/title-only bắt buộc unjudged. Có abstract nhưng thực sự không đủ để kết luận cũng ghi rõ lý do.

Đọc mỗi title + abstract và query trước khi quyết định. Không dùng keyword rules để tự động sinh nhãn, không suy kết quả không có trong abstract. Note tiếng Việt ngắn, nêu cụ thể nội dung trả lời hoặc thiếu so với query; lý do bắt buộc cho mọi cặp. Không chấm lại sau khi xem kết quả agent khác.

Mỗi dòng output có đúng các trường: query_id, doc_id, label, annotator, annotator_type, experimental, round, note. annotator=machine_A hoặc machine_B theo phân công; annotator_type=machine; experimental=true; round=independent. label là số nguyên 0/1/2 hoặc chuỗi unjudged. Không giả danh người A/B. Đây là thử nghiệm tham khảo, không hoàn tất SG-033.
''', encoding='utf-8')
print(json.dumps({'status': 'PASS', 'pairs': len(actual), 'queries': len(dev), 'abstract_missing': manifest['abstract_missing']}))
