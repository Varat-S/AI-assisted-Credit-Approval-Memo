"""Local setup checks; never call a model or print credentials."""
from importlib.util import find_spec


def check_vertex_setup(backend):
    from app.services.llm.providers_vertex import VertexProviderBackend
    if not isinstance(backend, VertexProviderBackend):
        return
    backend.check_configuration()
    try:
        installed = find_spec('google.genai') is not None
    except ModuleNotFoundError:
        installed = False
    if not installed:
        raise ValueError('Vertex SDK is missing. Run uv sync --locked --extra dev --extra vertex.')
    settings = backend._settings
    if settings.vertex_api_key and settings.vertex_api_key.get_secret_value():
        return
    import google.auth
    def no_network(*args, **kwargs):
        raise RuntimeError('Credential discovery requires a local credential configuration.')
    try:
        google.auth.default(request=no_network)
    except Exception:
        raise ValueError('Vertex application-default credentials are unavailable. Run gcloud auth application-default login '
                         'or configure GOOGLE_APPLICATION_CREDENTIALS for this machine.') from None


def main():
    from app.core.config import get_settings
    from app.services.llm.providers_vertex import VertexProviderBackend
    settings = get_settings()
    try:
        if settings.llm_provider == 'vertex':
            check_vertex_setup(VertexProviderBackend(settings))
        from app.models.base import create_engine_and_session, init_db
        engine, _ = create_engine_and_session('sqlite://')
        try:
            init_db(engine)
        finally:
            engine.dispose()
        print('Local setup checks passed. Database tables can be created from repository code.')
        print('No model was called. Provider model access and quota are checked by the provider during a live request.')
        return 0
    except Exception as exc:
        print('Setup check failed: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
