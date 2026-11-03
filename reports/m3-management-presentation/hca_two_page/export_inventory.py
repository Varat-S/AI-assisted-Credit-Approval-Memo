"""Inventory and render the recorded HCA run; never runs agents or ingestion."""
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

folder = Path(__file__).resolve().parent
repository = folder.parents[2]
sys.path.insert(0, str(repository))
os.environ['DEBUG'] = 'false'

from app.models.base import create_engine_and_session
from app.models.orm import ModelRun, StageArtifact
from app.services.bo.four_section_view import load_view, render_page

saved = repository / 'output/hca_live_saved/20261103_management'
manifest = json.loads((saved / 'saved_result_manifest.json').read_text(encoding='utf-8'))


def immutable():
    return all(sha256((saved / item['path']).read_bytes()).hexdigest() == item['sha256'] for item in manifest['files'])


assert immutable()
engine, factory = create_engine_and_session('sqlite:///' + (saved / 'case.db').as_posix())
with factory() as session:
    before = [(r.name, r.sha256, r.payload_json) for r in session.query(StageArtifact).all()]
    calls = session.query(ModelRun).count()
    view = load_view(session, 'ar_70066e79dd954e3c', 'HCA_2025_M3_PRESENTATION_LIVE_20261103')
    pdf = view['management']['pdf']
    eligible = [entry for entry in pdf['inventory'] if entry['eligible']]
    web = render_page(view)
    web_hash = sha256(web.encode('utf-8')).hexdigest()
    assert web_hash == '0c36fb49d6905b45a20a21a9c41f65cd97f4b0e933ac97597e3b68614dca0cc5'
    (folder / 'web_full.html').write_text(web, encoding='utf-8')
    (folder / 'print_full.html').write_text(render_page(view, pdf=True), encoding='utf-8')
    summary = {'run_id': 'ar_70066e79dd954e3c', 'finding_count': pdf['finding_count'],
               'eligible_excluded_by_categorization': pdf['eligible_excluded_by_categorization'],
               'eligible_review_statuses': dict(Counter(entry['review_status'] for entry in eligible)),
               'eligible_directions': dict(Counter(entry['direction'] for entry in eligible)),
               'entries': pdf['inventory'], 'sourced_executives': len(pdf['executives']),
               'monitoring_priorities': pdf['monitoring_priorities'], 'follow_up': pdf['follow_up'],
               'web_render_byte_identical': True, 'web_sha256': web_hash}
    (folder / 'inventory.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    assert [(r.name, r.sha256, r.payload_json) for r in session.query(StageArtifact).all()] == before
    assert session.query(ModelRun).count() == calls == 14
    proof = {'run_id': summary['run_id'], 'new_model_calls': 0, 'model_runs_before_and_after': calls,
             'frozen_stages_unchanged': True, 'frozen_stage_count': len(before),
             'canonical_files_unchanged': immutable(), 'canonical_files_verified': len(manifest['files']),
             'web_render_byte_identical': True, 'web_sha256': web_hash}
    (folder / 'immutability.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
engine.dispose()
assert immutable()
print(json.dumps(proof))
