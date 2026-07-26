"""Feature registry (PI-4 / S4.1).

Importing ``app.features.definitions`` fires every ``@register_feature`` into the
module-global default registry (the app/domains load pattern).
"""

from app.features.registry import (
    FeatureRegistry,
    RegisteredFeature,
    _DEFAULT_REGISTRY,
    _register,
    latest_view,
    register_feature,
)
from app.features.schema import (
    FeatureContext,
    FeatureDType,
    FeatureSource,
    FeatureSpec,
    FeatureValue,
    FeatureVector,
    FeatureView,
)


def get_feature_registry() -> FeatureRegistry:
    """The populated default registry (imports the seed catalog on first call)."""
    import app.features.definitions  # noqa: F401 — fires registration
    return _DEFAULT_REGISTRY


def default_view(registry: FeatureRegistry | None = None, *, settings=None) -> FeatureView:
    from app.core.config import get_settings
    settings = settings or get_settings()
    reg = registry or get_feature_registry()
    return latest_view(reg, name=settings.feat_default_view, version=1)


__all__ = [
    "FeatureRegistry", "RegisteredFeature", "FeatureContext", "FeatureDType",
    "FeatureSource", "FeatureSpec", "FeatureValue", "FeatureVector", "FeatureView",
    "register_feature", "get_feature_registry", "default_view", "latest_view",
]
