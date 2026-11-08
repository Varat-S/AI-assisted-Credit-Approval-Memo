import pytest
from app.core.config import Settings
from app.doctor import check_vertex_setup
from app.services.llm.providers_vertex import VertexProviderBackend


def backend(**kwargs):
    return VertexProviderBackend(Settings(_env_file=None, llm_provider='vertex',
        google_cloud_project='test-project', google_cloud_location='us',
        vertex_model_narrow='test-model', **kwargs))


def test_offline_backends_do_not_need_google_credentials():
    check_vertex_setup(object())
    check_vertex_setup(None)


def test_missing_vertex_sdk_stops_before_model_call(monkeypatch):
    monkeypatch.setattr('app.doctor.find_spec', lambda *a: None)
    with pytest.raises(ValueError, match='Vertex SDK is missing'):
        check_vertex_setup(backend())


def test_missing_adc_has_actionable_error_without_disclosing_exception(monkeypatch):
    monkeypatch.setattr('app.doctor.find_spec', lambda *a: object())
    import google.auth
    def fail(**kwargs): raise RuntimeError('sensitive credential detail')
    monkeypatch.setattr(google.auth, 'default', fail)
    with pytest.raises(ValueError) as error: check_vertex_setup(backend())
    assert 'application-default login' in str(error.value)
    assert 'sensitive' not in str(error.value)


def test_api_key_setup_does_not_require_adc(monkeypatch):
    monkeypatch.setattr('app.doctor.find_spec', lambda *a: object())
    import google.auth
    monkeypatch.setattr(google.auth, 'default', lambda **kw: pytest.fail('ADC not used for API key'))
    check_vertex_setup(backend(vertex_api_key='test-only-key'))
