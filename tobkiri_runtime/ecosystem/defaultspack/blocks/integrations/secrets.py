from blocks._common import ok, error
from domain.integrations.secrets import (
    integration_secret_keys,
    integration_secret_status,
    load_integration_secrets_into_env,
    set_integration_secret,
)


def run(input_data, context):
    method = str(input_data.get("_method") or "GET").upper()
    if method == "GET":
        return ok(
            {
                "providers": integration_secret_status(),
                "available_keys": {
                    provider: integration_secret_keys(provider)
                    for provider in ("discord", "line", "slack")
                },
            }
        )

    provider = str(input_data.get("provider") or "").strip()
    key = str(input_data.get("key") or "").strip()
    value = str(input_data.get("value") or "")
    if not provider or not key:
        return error("provider and key are required", "INVALID_INPUT")
    result = set_integration_secret(provider, key, value)
    if not result.get("success"):
        return error(str(result.get("error") or "failed to save integration secret"), "INVALID_INPUT")
    load_integration_secrets_into_env()
    return ok(result)
