"""Offline diagnostic: python this_file.py REPOSITORY OUTPUT_JSON."""
import json
import locale
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

repository = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repository))

from app.core.config import Settings, get_settings
from app.core.hashing import content_hash
from app.models.base import create_engine_and_session, init_db
from app.models.orm import StageArtifact
from app.schemas.bo_four_section import FILENAME
from app.services.bo.four_section import assemble, persist
from app.services.bo.workbench import bo_artifact
from tests import four_section_helpers as helpers
from tests.integration.test_bo_four_section_independent import build

Settings.model_config['env_file'] = None
get_settings.cache_clear()


def differences(expected, actual, pointer=''):
    if isinstance(expected, dict) and isinstance(actual, dict):
        return [d for key in expected for d in differences(expected[key], actual[key], pointer + '/' + str(key))]
    if isinstance(expected, list) and isinstance(actual, list):
        return [d for i, (left, right) in enumerate(zip(expected, actual))
                for d in differences(left, right, pointer + '/' + str(i))]
    return [] if expected == actual else [{'pointer': pointer, 'expected': expected, 'default_decoded': actual}]


records = []
for repeat in range(2):
    for producer in ('four_section', 'independent'):
        engine, factory = create_engine_and_session('sqlite://')
        init_db(engine)
        with factory() as session, TemporaryDirectory(prefix='serialization-proof-', dir=repository) as temporary:
            folder = Path(temporary)
            if producer == 'four_section':
                result, _ = helpers.run(session, folder)
                memo = result.four_section_memo
                path = result.output_paths[FILENAME]
            else:
                result, saved = build(session, folder)
                memo = assemble(saved)
                path = folder / 'independent-roundtrip.json'
                persist(session, saved, memo, path=path)
            default = json.loads(path.read_text())
            utf8 = json.loads(path.read_text(encoding='utf-8'))
            database = bo_artifact(session, result.analysis_run_id, kind='four_section')
            before = [(row.name, row.sha256, row.payload_json) for row in session.query(StageArtifact).all()]
            file_hash = sha256(path.read_bytes()).hexdigest()
            adapter_available = (repository / 'app/services/bo/management_view.py').exists()
            if adapter_available:
                from app.services.bo.four_section_view import load_view, render_page
                view = load_view(session, result.analysis_run_id)
                render_page(view)
                render_page(view, pdf=True)
            after = [(row.name, row.sha256, row.payload_json) for row in session.query(StageArtifact).all()]
            records.append({'repeat': repeat + 1, 'producer': producer,
                            'differences': differences(memo, default),
                            'utf8_equals_database_and_original': utf8 == database == memo,
                            'recorded_hash_unchanged': utf8['content_hash'] == database['content_hash'] == memo['content_hash'],
                            'utf8_content_hash': content_hash(utf8), 'original_content_hash': content_hash(memo),
                            'adapter_available': adapter_available,
                            'file_sha256_unchanged_after_render': file_hash == sha256(path.read_bytes()).hexdigest(),
                            'stage_bytes_and_hashes_unchanged_after_render': before == after})
        engine.dispose()

Path(sys.argv[2]).write_text(json.dumps({'repository': str(repository),
    'default_encoding': locale.getencoding(), 'records': records}, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
