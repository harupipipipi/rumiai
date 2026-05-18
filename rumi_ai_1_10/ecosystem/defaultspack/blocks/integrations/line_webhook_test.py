from __future__ import annotations

from domain.integrations.line.inbound import simulate_webhook


def run(input_data, context):
    return simulate_webhook(input_data, context)
