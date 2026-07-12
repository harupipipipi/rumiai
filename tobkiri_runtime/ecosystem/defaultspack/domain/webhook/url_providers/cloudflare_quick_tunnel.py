from __future__ import annotations

import sys as _sys

from domain.webhook_url_providers.cloudflare_quick_tunnel import provider as _component


_legacy_name = __name__
globals().update(_component.__dict__)
_sys.modules[_legacy_name] = _component
