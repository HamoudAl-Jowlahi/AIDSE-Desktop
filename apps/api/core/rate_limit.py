"""
AIDSE Platform — Rate Limiting (Section 13.6)

slowapi-based IP limiter. Auth endpoints are the brute-force surface:
  login/register: 5/minute per IP
  refresh:        30/minute per IP
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from apps.api.core.config import get_settings

# Disabled wholesale in the test suite (conftest sets RATE_LIMIT_ENABLED=false)
limiter = Limiter(key_func=get_remote_address, enabled=get_settings().RATE_LIMIT_ENABLED)
