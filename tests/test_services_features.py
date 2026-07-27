from app.features.store import FeatureStore
from tests.conftest import make_services


def test_services_bundle_has_feature_store_sharing_candidate_db(settings):
    services = make_services(settings)
    assert isinstance(services.features, FeatureStore)
    # Shares the candidate DB session factory so FK-linked vectors persist.
    assert services.features._session_factory is services.candidates._session_factory
