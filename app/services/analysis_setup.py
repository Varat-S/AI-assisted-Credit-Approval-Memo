"""Read-only setup contract. No jobs, model generations or approval actions.

Registry entries select existing source packages. The returned parameter map
matches /run/start, but this milestone deliberately never submits it there.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services.acquisition import shared_filing
from app.services.pipeline.package import SourcePackage
from app.services.fo.runner import validate_case_id

REGISTRY_PATH = Path(__file__).resolve().parents[2] / 'config' / 'analysis_companies.json'


class SetupError(ValueError):
    pass


def company_registry():
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        rows = data['companies']
        if data['version'] != 1 or not rows or len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Invalid registry')
        for row in rows:
            for key in ('id', 'label', 'ticker', 'cik', 'report_date', 'filing_folder', 'source_package'):
                if not isinstance(row[key], str) or not row[key].strip():
                    raise ValueError('Invalid registry entry')
        return rows
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SetupError('Company setup is unavailable. Ask the administrator to check the company registry.') from exc


@dataclass(frozen=True)
class SetupSelection:
    company: dict
    evidence: dict
    sections: str
    validation_mode: str
    case_id: str
    cutoff: datetime

    @property
    def exploratory(self):
        return self.validation_mode == 'exploratory'

    @property
    def approval_policy(self):
        # Standard setup is not an approval or a promise of future eligibility.
        return 'ineligible_for_final_approval' if self.exploratory else 'existing_review_and_approval_required'

    def backend_parameters(self):
        return {'folder': self.company['filing_folder'], 'case_id': self.case_id,
                'sections': self.sections, 'cutoff': self.cutoff.isoformat(),
                'bo_validators': 'off' if self.exploratory else 'on'}


def validate_setup(*, company='hca', sections='both', validation_mode='standard',
                   cutoff='', case_id=''):
    spec = next((c for c in company_registry() if c['id'] == company), None)
    if spec is None:
        raise SetupError('Select an available hospital company.')
    if sections not in {'both', 'bo'}:
        raise SetupError('Choose Business + Financial Overview or Business Overview Only.')
    if validation_mode not in {'standard', 'exploratory'}:
        raise SetupError('Choose Standard Mode or Exploratory Mode.')
    case_id = case_id.strip()
    if case_id:
        try:
            validate_case_id(case_id)
        except ValueError as exc:
            raise SetupError(str(exc)) from exc
    root = shared_filing.filings_root()
    folder = (root / spec['filing_folder']).resolve()
    path = (folder / spec['source_package']).resolve()
    if folder.parent != root or path.parent != folder:
        raise SetupError('The configured evidence package must stay inside its filing folder.')
    try:
        if not any(r['name'] == spec['filing_folder'] and r['runnable']
                   for r in shared_filing.list_shared()):
            raise ValueError('The shared filing is not ready for the existing browser backend')
        package = SourcePackage.load(path)
        matches = [b.bundle for b in package.sec_bundles
                   if int(b.bundle.cik) == int(spec['cik'])
                   and b.bundle.report_date.isoformat() == spec['report_date']
                   and b.bundle.form == '10-K']
        if len(matches) != 1 or package.as_of_date.isoformat() != spec['report_date']:
            raise ValueError('Wrong company or reporting period')
        if len(package.sec_bundles) != 1 or any(int(b.bundle.cik) != int(spec['cik']) for b in package.sec_bundles):
            raise ValueError('Unexpected company evidence')
        identity = next(e for e in package.entities if e.entity_id == package.borrower_entity_id)
        if spec['ticker'] not in identity.tickers:
            raise ValueError('Wrong borrower identity')
        # The future /run/start endpoint reads the shared manifest directly.
        # Prove it names exactly the bundle selected by the source package.
        shared = shared_filing.load_bundle(spec['filing_folder'])
        selected = matches[0]
        if not any(f.role == 'schema' for f in selected.files):
            raise ValueError('Shared filing schema is missing')
        if shared.accession != selected.accession or shared.cik.lstrip('0') != selected.cik.lstrip('0'):
            raise ValueError('Shared filing differs from source package')
        if {f.filename: f.sha256 for f in shared.files} != {f.filename: f.sha256 for f in selected.files}:
            raise ValueError('Shared filing content differs from source package')
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        raise SetupError(f'{spec["label"]}’s required FY{spec["report_date"][:4]} evidence package is unavailable or does not match its configuration. '
                         'Restore the original filing files, bundle.json and package.json before continuing.') from exc
    effective_cutoff = package.evidence_cutoff_timestamp
    if cutoff.strip():
        try:
            effective_cutoff = datetime.fromisoformat(cutoff.strip().replace('Z', '+00:00'))
            if effective_cutoff.tzinfo is None:
                raise ValueError('Timezone required')
        except ValueError as exc:
            raise SetupError('Enter an evidence cutoff with a timezone, for example 2025-03-31T23:59:59Z.') from exc
    primary = next(f for f in selected.files if f.filename == selected.primary_document)
    if effective_cutoff < primary.available_at:
        raise SetupError('The evidence cutoff must include the selected annual report’s availability date: '
                         + primary.available_at.isoformat())
    evidence = {'report_date': selected.report_date, 'filing_date': selected.filing_date,
                'cutoff': effective_cutoff.astimezone(timezone.utc),
                'configured_cutoff': package.evidence_cutoff_timestamp,
                'accession': selected.accession, 'primary_document': selected.primary_document,
                'folder': spec['filing_folder'], 'package_file': spec['source_package'],
                'sources': len(selected.files)}
    return SetupSelection(spec, evidence, sections, validation_mode, case_id, effective_cutoff)


def provider_configuration(sections):
    """Reuse configuration checks only; never refresh credentials or call an API."""
    from app.services.bo_fo import bo_live_backend
    from app.services.fo.precheck import agent_available
    try:
        bo_live_backend()  # Its existing configuration check is local and lazy.
        bo_ok, bo_reason = True, None
    except Exception:
        bo_ok, bo_reason = False, 'Business Overview provider configuration is unavailable.'
    try:
        fo_ok, fo_reason = agent_available() if sections == 'both' else (True, None)
    except Exception:
        fo_ok, fo_reason = False, 'Financial Overview provider configuration is unavailable.'
    return {'configured': bo_ok and fo_ok, 'bo_configured': bo_ok,
            'fo_configured': fo_ok, 'bo_reason': bo_reason, 'fo_reason': fo_reason}
