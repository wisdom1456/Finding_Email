"""Rate limiter configuration for the API."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared rate limiter instance
# Uses IP address by default, with generous limits for legitimate usage
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
