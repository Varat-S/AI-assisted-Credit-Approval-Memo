"""SEC-backed setup downloads and case-associated corporate structure uploads."""
import json
import os
from pathlib import Path
import re
import tempfile
import threading

from app.services.acquisition import shared_filing
from app.services.acquisition.sec_edgar import EdgarError
from app.services.analysis_setup import _configured_companies, company_registry
from app.services.bo.m3_rebuild.structure import validate_structure_input

_lock = threading.Lock()
MAX_STRUCTURE_BYTES = 1024 * 1024


def _check_bundle(bundle, spec):
    if (int(bundle.cik) != int(spec['cik']) or bundle.ticker != spec['ticker']
            or bundle.form != '10-K' or bundle.report_date.isoformat() != spec['report_date']
            or not any(f.role == 'schema' for f in bundle.files)):
        raise ValueError('Filing does not match the configured company, reporting year and XBRL schema.')


def download_files(client_factory):
    """Fetch configured company/year targets from SEC; never read a bundled archive.

    Already available, hash-verified filings are reused without network requests.
    Existing incomplete/conflicting folders are preserved and reported.
    """
    if not _lock.acquire(blocking=False):
        raise ValueError('Another file operation is running. Please wait and try again.')
    try:
        specs = _configured_companies()
        results, client = [], None
        for spec in specs:
            folder = shared_filing.filings_root() / spec['filing_folder']
            try:
                if folder.exists():
                    _check_bundle(shared_filing.load_bundle(spec['filing_folder']), spec)
                    results.append({'folder': folder.name, 'status': 'Already available'})
                    continue
                if client is None:
                    client = client_factory()
                # Resolve an official accession first, before creating any local folder.
                _, _, filing = shared_filing.select_annual_filing(
                    client, spec['ticker'], fy=int(spec['report_date'][:4]))
                if filing.report_date.isoformat() != spec['report_date'] or int(filing.cik) != int(spec['cik']):
                    raise ValueError('SEC filing identity or period does not match the configured target.')
                shared = shared_filing.fetch_filing(client, spec['ticker'], accession=filing.accession,
                                                    with_proxy=True, name=spec['filing_folder'])
                _check_bundle(shared_filing.load_bundle(shared.name), spec)
                results.append({'folder': shared.name, 'status': 'Downloaded from SEC'})
            except ContactRequired:
                raise
            except (ValueError, OSError, EdgarError) as exc:
                # SEC errors deliberately contain no contact email or credential values.
                results.append({'folder': spec['filing_folder'], 'status': 'Failed',
                                'error': str(exc)})
        return {'results': results, 'message':
                'No companies are configured for download.' if not specs else
                f"{sum(r['status'] != 'Failed' for r in results)} of {len(specs)} filing packages ready."}
    finally:
        _lock.release()


class ContactRequired(ValueError):
    pass


def _company_key(name):
    words = re.findall(r'[a-z0-9]+', name.lower())
    return ' '.join(w for w in words if w not in {'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd'})


def save_structure(company_id, content):
    """Validate before atomically saving under the selected company's filing folder."""
    if len(content) > MAX_STRUCTURE_BYTES:
        raise ValueError('Corporate structure JSON must be 1 MB or smaller.')
    try:
        document = json.loads(content.decode("utf-8-sig"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError('Choose a valid UTF-8 JSON file.') from exc
    validate_structure_input(document)
    spec = next((row for row in company_registry() if row['id'] == company_id), None)
    if spec is None:
        raise ValueError('Select an available company before uploading its corporate structure.')
    folder = shared_filing.fo_loader.resolve_folder(spec['filing_folder'])
    identity = shared_filing.company_info(folder.name)
    names = [identity.get('name', ''), spec.get('name', ''), spec['label'].split('(')[0].strip()]
    if _company_key(document['company_name']) not in {_company_key(n) for n in names if n}:
        raise ValueError('The JSON company_name must match the selected company.')
    if not _lock.acquire(blocking=False):
        raise ValueError('Another file operation is running. Please wait and try again.')
    temp = None
    try:
        target = folder / shared_filing.M3_STRUCTURE
        if target.is_symlink():
            raise ValueError('Corporate structure destination cannot be a symbolic link.')
        # Keep prior uploads outside the filing root so discovery never sees duplicates.
        if target.exists() and target.read_bytes() != content:
            from app.core.config import get_settings
            from hashlib import sha256
            backup = Path(get_settings().data_dir) / 'corporate_structure_history' / folder.name
            backup.mkdir(parents=True, exist_ok=True)
            previous = target.read_bytes()
            (backup / (sha256(previous).hexdigest() + '.json')).write_bytes(previous)
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.corporate-', suffix='.tmp', delete=False) as file:
            temp = Path(file.name)
            file.write(content)
        os.replace(temp, target)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        _lock.release()
    return {'message': f"Corporate structure saved for {spec['label']}.",
            'data_status': document['data_status'], 'company': company_id,
            'simulated': 'simulat' in document['data_status'].lower()}
