"""Domain plug-ins. Importing this package registers the built-in domains.

Adding a domain = drop one module here and decorate it with ``@register_domain``.
"""

from app.domains import data_eng as _data_eng  # noqa: F401  (registers "data_eng")
from app.domains import genai as _genai  # noqa: F401  (registers "genai")

__all__ = ["_data_eng", "_genai"]
