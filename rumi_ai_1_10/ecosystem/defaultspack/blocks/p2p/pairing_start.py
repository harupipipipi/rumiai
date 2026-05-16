from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok
from blocks.p2p._helpers import settings_from
from domain.p2p.pairing import PairingManager


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    settings = settings_from(input_data, context)
    manager = PairingManager(settings.store_path)
    session = manager.start_pairing(
        peer_id=str(input_data.get("peer_id") or ""),
        peer_fingerprint=str(input_data.get("peer_fingerprint") or input_data.get("fingerprint") or ""),
        peer_label=str(input_data.get("peer_label") or input_data.get("label") or ""),
        ttl_seconds=int(input_data.get("ttl_seconds") or settings.pairing_ttl_seconds),
        capabilities=input_data.get("capabilities") if isinstance(input_data.get("capabilities"), list) else None,
        allowed_company_ids=input_data.get("allowed_company_ids") if isinstance(input_data.get("allowed_company_ids"), list) else None,
        settings=settings,
    )
    return ok({"pairing": session.as_dict()})
