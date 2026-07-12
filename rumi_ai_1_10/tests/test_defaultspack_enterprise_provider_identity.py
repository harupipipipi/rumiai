from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK))

from domain.ai_client.enterprise_provider_identity import (  # noqa: E402
    IDENTITY_FIELDS,
    enterprise_scope,
    normalize_enterprise_identity,
    qualified_deployment_id,
)
from domain.ai_client.providers import (  # noqa: E402
    _instantiate_manifest_provider,
    detect_available_providers,
    get_provider_catalog_map,
)
from domain.ai_client.providers.enterprise_native_providers import (  # noqa: E402
    BedrockProvider,
    OCIProvider,
    SnowflakeCortexProvider,
    VertexAIProvider,
    WatsonxProvider,
)
from domain.components.registry import get_domain_component_registry  # noqa: E402


def _identity(provider_id):
    return {field: f"private-{field}" for field in IDENTITY_FIELDS[provider_id]}


def test_enterprise_scope_is_stable_isolated_and_opaque(tmp_path):
    key = tmp_path / "scope.key"
    first = enterprise_scope("aws-bedrock", _identity("aws-bedrock"), key_path=key)
    same = enterprise_scope("aws-bedrock", _identity("aws-bedrock"), key_path=key)
    changed = enterprise_scope("aws-bedrock", {**_identity("aws-bedrock"), "region": "other"}, key_path=key)
    assert first == same
    assert first != changed
    assert "private" not in first


def test_deployment_qualification_never_flattens_control_plane_identity(tmp_path, monkeypatch):
    monkeypatch.setattr("domain.ai_client.enterprise_provider_identity._local_key", lambda _path: b"x" * 32)
    identity = _identity("azure-openai")
    qualified = qualified_deployment_id("azure-openai", identity, "gpt-family")
    assert qualified.startswith("azure-openai/")
    assert qualified.endswith(":gpt-family")
    assert identity["resource"] not in qualified
    assert identity["deployment"] not in qualified


def test_enterprise_identity_rejects_missing_dimensions():
    with pytest.raises(ValueError, match="endpoint"):
        normalize_enterprise_identity("databricks-model-serving", {"workspace": "one"})


def test_enterprise_matrix_registered_with_explicit_native_boundaries():
    get_domain_component_registry(force_reload=True)
    catalog = get_provider_catalog_map()
    assert set(IDENTITY_FIELDS) <= set(catalog)
    for provider_id, fields in IDENTITY_FIELDS.items():
        payload = json.loads((DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(encoding="utf-8"))
        manifest = payload["provider_manifest"]
        assert manifest["config"]["identity_fields"] == list(fields)
        assert manifest["config"]["inventory_scope"] == "account_project_region"
        assert manifest["config"]["source_docs"].startswith("https://")
        assert "default_model" not in manifest
        assert manifest["supports_invoke"] is True
        assert manifest["catalog_only"] is False


def _manifest(provider_id):
    payload = json.loads(
        (DEFAULTSPACK / "domain" / "providers" / provider_id / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return payload["provider_manifest"]


def test_native_enterprise_entrypoints_instantiate_without_network():
    get_domain_component_registry(force_reload=True)
    expected = {
        "aws-bedrock": BedrockProvider,
        "google-vertex-ai": VertexAIProvider,
        "ibm-watsonx": WatsonxProvider,
        "oracle-oci-generative-ai": OCIProvider,
        "snowflake-cortex": SnowflakeCortexProvider,
    }
    for provider_id, expected_type in expected.items():
        provider = _instantiate_manifest_provider(_manifest(provider_id))
        assert isinstance(provider, expected_type)
        assert provider.list_models() == []


def test_official_credential_chain_activation_is_lazy_and_network_free(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-1")
    monkeypatch.setenv("OCI_CONFIG_FILE", "not-opened-until-refresh")
    monkeypatch.setenv("SNOWFLAKE_CONNECTION_NAME", "configured-connection")
    available = detect_available_providers()
    assert {
        "aws-bedrock",
        "google-vertex-ai",
        "oracle-oci-generative-ai",
        "snowflake-cortex",
    } <= set(available)


class _BedrockControl:
    def list_foundation_models(self):
        return {
            "modelSummaries": [
                {
                    "modelId": "vendor/model:1",
                    "modelName": "Model One",
                    "outputModalities": ["TEXT"],
                }
            ]
        }

    def list_inference_profiles(self, **_kwargs):
        return {
            "inferenceProfileSummaries": [
                {"inferenceProfileId": "profile-1", "inferenceProfileName": "Profile One"}
            ]
        }


class _BedrockRuntime:
    def __init__(self):
        self.request = None

    def converse(self, **kwargs):
        self.request = kwargs
        return {
            "output": {"message": {"content": [{"text": "bedrock answer"}]}},
            "usage": {"inputTokens": 2, "outputTokens": 3},
        }


def test_bedrock_uses_control_plane_and_converse_without_flattening_identity():
    runtime = _BedrockRuntime()

    def factory(service, _region, _profile):
        return _BedrockControl() if service == "bedrock" else runtime

    provider = BedrockProvider(sdk_factory=factory)
    models = provider.list_models(refresh=True)
    assert {model["model_id"] for model in models} == {"vendor/model:1", "profile-1"}
    response = provider.complete(
        "aws-bedrock/vendor/model:1",
        [{"role": "user", "content": "hello"}],
        [],
        {"maxTokens": 64},
    )
    assert response["content"][0]["text"] == "bedrock answer"
    assert runtime.request["modelId"] == "vendor/model:1"


class _GoogleResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _GoogleSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return _GoogleResponse(
            {"models": [{"name": "projects/p/locations/r/models/custom-model"}]}
        )

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _GoogleResponse(
            {
                "candidates": [{"content": {"parts": [{"text": "vertex answer"}]}}],
                "usageMetadata": {"promptTokenCount": 1},
            }
        )


def test_vertex_uses_adc_session_and_project_location_scope(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-1")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    session = _GoogleSession()
    provider = VertexAIProvider(session_factory=lambda: session)
    assert provider.list_models(refresh=True)[0]["model_id"] == "custom-model"
    response = provider.complete(
        "google-vertex-ai/gemini-model",
        [{"role": "user", "content": "hello"}],
        [],
        {},
    )
    assert response["content"][0]["text"] == "vertex answer"
    assert "/projects/project-1/locations/us-central1/" in session.calls[-1][1]


class _HTTPResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


class _WatsonOpener:
    def __init__(self):
        self.requests = []

    def __call__(self, request, **_kwargs):
        self.requests.append(request)
        if "foundation_model_specs" in request.full_url:
            return _HTTPResponse(
                {"resources": [{"model_id": "ibm/granite", "label": "Granite"}]}
            )
        return _HTTPResponse(
            {"choices": [{"message": {"content": "watson answer"}}], "usage": {}}
        )


def test_watsonx_inventory_and_chat_preserve_project_scope(monkeypatch):
    monkeypatch.setenv("WATSONX_IAM_TOKEN", "test-token")
    monkeypatch.setenv("WATSONX_PROJECT_ID", "project-1")
    opener = _WatsonOpener()
    provider = WatsonxProvider(opener=opener)
    assert provider.list_models(refresh=True)[0]["model_id"] == "ibm/granite"
    response = provider.complete(
        "ibm-watsonx/ibm/granite",
        [{"role": "user", "content": "hello"}],
        [],
        {},
    )
    assert response["content"][0]["text"] == "watson answer"
    body = json.loads(opener.requests[-1].data)
    assert body["project_id"] == "project-1"


class _OCIItem:
    id = "ocid1.generativeaimodel.model-1"
    display_name = "OCI Model"
    capabilities = ["CHAT"]


class _OCIData:
    items = [_OCIItem()]


class _OCIResponse:
    data = _OCIData()
    headers = {}


class _OCIControl:
    def list_models(self, **_kwargs):
        return _OCIResponse()


class _OCIText:
    text = "oci answer"


class _OCIMessageResponse:
    content = [_OCIText()]


class _OCIChoice:
    message = _OCIMessageResponse()


class _OCIChatResponse:
    choices = [_OCIChoice()]


class _OCIRuntimeData:
    chat_response = _OCIChatResponse()


class _OCIRuntimeResponse:
    data = _OCIRuntimeData()


class _OCIRuntime:
    def chat(self, _details):
        return _OCIRuntimeResponse()


class _OCIModels:
    class _Value:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    OnDemandServingMode = _Value
    Message = _Value
    TextContent = _Value
    GenericChatRequest = _Value
    ChatDetails = _Value


def test_oci_uses_sdk_configuration_boundary(monkeypatch):
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    provider = OCIProvider(sdk_factory=lambda: (_OCIControl(), _OCIRuntime(), _OCIModels))
    assert provider.list_models(refresh=True)[0]["model_id"].startswith("ocid1.")
    response = provider.complete(
        "oracle-oci-generative-ai/ocid1.generativeaimodel.model-1",
        [{"role": "user", "content": "hello"}],
        [],
        {},
    )
    assert response["content"][0]["text"] == "oci answer"


class _SnowflakeCursor:
    description = [
        ("name",),
        ("lifecycle_status",),
        ("available_regions",),
        ("legacy_date",),
        ("eol_date",),
    ]

    def __init__(self):
        self.sql = []

    def execute(self, statement, params=None):
        self.sql.append((statement, params))
        return self

    def fetchall(self):
        return [("MODEL-A", "GA", '["AWS_US_EAST_1"]', None, None)]

    def fetchone(self):
        return ('{"response":"snowflake answer","usage":{}}',)

    def close(self):
        return None


class _SnowflakeConnection:
    def __init__(self):
        self.cursors = []

    def cursor(self):
        cursor = _SnowflakeCursor()
        self.cursors.append(cursor)
        return cursor

    def close(self):
        return None


def test_snowflake_uses_account_visible_cortex_inventory_and_bound_sql():
    connections = []

    def factory():
        connection = _SnowflakeConnection()
        connections.append(connection)
        return connection

    provider = SnowflakeCortexProvider(connector_factory=factory)
    assert provider.list_models(refresh=True)[0]["model_id"] == "MODEL-A"
    response = provider.complete(
        "snowflake-cortex/MODEL-A",
        [{"role": "user", "content": "hello"}],
        [],
        {},
    )
    assert response["content"][0]["text"] == "snowflake answer"
    statement, params = connections[-1].cursors[0].sql[-1]
    assert "%s" in statement
    assert params[0] == "MODEL-A"
