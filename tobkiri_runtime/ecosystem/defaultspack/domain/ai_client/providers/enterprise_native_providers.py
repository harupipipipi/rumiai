"""Native enterprise provider adapters with official credential chains."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..base_provider import BaseProvider


class EnterpriseProviderError(RuntimeError):
    """Stable enterprise-provider error without credential or tenant disclosure."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class EnterpriseNativeProvider(BaseProvider):
    """Common manifest model ownership for native enterprise adapters."""

    provider_id = ""
    manifest_factory = True

    def __init__(self, *, known_models: list[dict[str, Any]] | None = None) -> None:
        self._known_models = [dict(item) for item in (known_models or [])]

    @classmethod
    def from_manifest(
        cls,
        manifest: dict[str, Any],
        *,
        model_manifests: list[dict[str, Any]] | None = None,
    ) -> "EnterpriseNativeProvider":
        """Create from a trusted manifest without contacting a control plane."""
        return cls(known_models=model_manifests)

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return the official snapshot unless an explicit refresh is requested."""
        return [dict(item) for item in self._known_models]

    def _model_id(self, model: str) -> str:
        value = str(model or "").strip()
        prefix = f"{self.provider_id}/"
        return value[len(prefix) :] if value.startswith(prefix) else value

    @staticmethod
    def _standard_response(text: str, usage: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": str(text or "")}],
            "finish_reason": "stop",
            "usage": dict(usage or {}),
        }

    @staticmethod
    def _missing_dependency(package: str) -> EnterpriseProviderError:
        return EnterpriseProviderError(
            "missing_dependency",
            f"Install the enterprise provider extra containing {package}",
        )


class BedrockProvider(EnterpriseNativeProvider):
    """Amazon Bedrock Converse with the standard boto3 credential chain."""

    provider_id = "aws-bedrock"

    def __init__(self, *, known_models=None, sdk_factory=None) -> None:
        super().__init__(known_models=known_models)
        self._sdk_factory = sdk_factory
        self._region = str(os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "").strip()
        self._profile = str(os.environ.get("AWS_PROFILE") or "").strip()

    def _client(self, service: str):
        if self._sdk_factory is not None:
            return self._sdk_factory(service, self._region, self._profile)
        try:
            import boto3
        except ImportError as exc:
            raise self._missing_dependency("boto3") from exc
        session = boto3.Session(
            profile_name=self._profile or None,
            region_name=self._region or None,
        )
        return session.client(service)

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        control = self._client("bedrock")
        raw = control.list_foundation_models()
        models = [self._bedrock_model(item, "foundation_model") for item in raw.get("modelSummaries", [])]
        token = ""
        while hasattr(control, "list_inference_profiles"):
            kwargs = {"nextToken": token} if token else {}
            page = control.list_inference_profiles(**kwargs)
            models.extend(
                self._bedrock_model(item, "inference_profile")
                for item in page.get("inferenceProfileSummaries", [])
            )
            token = str(page.get("nextToken") or "")
            if not token:
                break
        return [model for model in models if model.get("model_id")]

    def _bedrock_model(self, raw: dict[str, Any], source: str) -> dict[str, Any]:
        model_id = str(raw.get("modelId") or raw.get("inferenceProfileId") or raw.get("inferenceProfileArn") or "")
        output = {str(item).upper() for item in raw.get("outputModalities", [])}
        return {
            "id": f"{self.provider_id}/{model_id}",
            "model_id": model_id,
            "display_name": str(raw.get("modelName") or raw.get("inferenceProfileName") or model_id),
            "type": "image" if "IMAGE" in output and "TEXT" not in output else "embedding" if "EMBEDDING" in output else "chat",
            "metadata": {"source": source, "capability_provenance": "bedrock_control_plane"},
        }

    @staticmethod
    def _messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        system: list[dict[str, Any]] = []
        converted: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content", "")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            if role == "system":
                system.append({"text": text})
            else:
                converted.append({"role": "assistant" if role == "assistant" else "user", "content": [{"text": text}]})
        return converted, system

    def complete(self, model, messages, tools, params):
        converted, system = self._messages(messages)
        kwargs: dict[str, Any] = {"modelId": self._model_id(model), "messages": converted}
        if system:
            kwargs["system"] = system
        inference = {
            key: value
            for key, value in dict(params or {}).items()
            if key in {"maxTokens", "temperature", "topP", "stopSequences"}
        }
        if inference:
            kwargs["inferenceConfig"] = inference
        if tools:
            kwargs["toolConfig"] = {"tools": tools}
        raw = self._client("bedrock-runtime").converse(**kwargs)
        output = raw.get("output", {}).get("message", {}).get("content", [])
        text = "".join(str(item.get("text") or "") for item in output if isinstance(item, dict))
        return self._standard_response(text, raw.get("usage"))

    def stream(self, model, messages, tools, params):
        converted, system = self._messages(messages)
        kwargs: dict[str, Any] = {"modelId": self._model_id(model), "messages": converted}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["toolConfig"] = {"tools": tools}
        response = self._client("bedrock-runtime").converse_stream(**kwargs)
        for event in response.get("stream", []):
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            if delta.get("text"):
                yield {"type": "content_delta", "delta": {"type": "text", "text": delta["text"]}}
            if event.get("messageStop") is not None:
                yield {"type": "stream_end", "finish_reason": "stop", "usage": {}}


class VertexAIProvider(EnterpriseNativeProvider):
    """Vertex AI REST adapter using Google Application Default Credentials."""

    provider_id = "google-vertex-ai"
    _SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]

    def __init__(self, *, known_models=None, session_factory=None) -> None:
        super().__init__(known_models=known_models)
        self._session_factory = session_factory
        self._project = str(os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()
        self._location = str(os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
        except ImportError as exc:
            raise self._missing_dependency("google-auth") from exc
        credentials, discovered_project = google.auth.default(scopes=self._SCOPES)
        if not self._project:
            self._project = str(discovered_project or "")
        return AuthorizedSession(credentials)

    def _root(self) -> str:
        if not self._project or not self._location:
            raise EnterpriseProviderError("configuration_error", "Vertex project and location are required")
        return f"https://{self._location}-aiplatform.googleapis.com/v1/projects/{urllib.parse.quote(self._project, safe='')}/locations/{urllib.parse.quote(self._location, safe='')}"

    @staticmethod
    def _json_response(response) -> dict[str, Any]:
        if int(getattr(response, "status_code", 200)) >= 400:
            raise EnterpriseProviderError("provider_error", "Vertex AI request failed")
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        models: list[dict[str, Any]] = []
        token = ""
        session = self._session()
        while True:
            params = {"pageSize": 100, **({"pageToken": token} if token else {})}
            raw = self._json_response(session.get(self._root() + "/models", params=params, timeout=30))
            for item in raw.get("models", []) if isinstance(raw.get("models"), list) else []:
                name = str(item.get("name") or "")
                model_id = name.rsplit("/", 1)[-1]
                if model_id:
                    models.append({"id": f"{self.provider_id}/{model_id}", "model_id": model_id, "type": "chat", "metadata": {"resource_name": name, "source": "vertex_models_api"}})
            token = str(raw.get("nextPageToken") or "")
            if not token:
                break
        return models or super().list_models()

    @staticmethod
    def _contents(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        contents: list[dict[str, Any]] = []
        system_parts: list[dict[str, str]] = []
        for message in messages:
            role = str(message.get("role") or "user")
            text = message.get("content", "")
            text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
            if role == "system":
                system_parts.append({"text": text})
            else:
                contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": text}]})
        return contents, {"parts": system_parts} if system_parts else None

    def complete(self, model, messages, tools, params):
        model_id = urllib.parse.quote(self._model_id(model), safe="")
        contents, system = self._contents(messages)
        body: dict[str, Any] = {"contents": contents, "generationConfig": dict(params or {})}
        if system:
            body["systemInstruction"] = system
        if tools:
            body["tools"] = tools
        url = self._root() + f"/publishers/google/models/{model_id}:generateContent"
        raw = self._json_response(self._session().post(url, json=body, timeout=120))
        parts = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "".join(str(item.get("text") or "") for item in parts if isinstance(item, dict))
        usage = raw.get("usageMetadata") if isinstance(raw.get("usageMetadata"), dict) else {}
        return self._standard_response(text, usage)


class WatsonxProvider(EnterpriseNativeProvider):
    """watsonx.ai native REST adapter with IBM Cloud IAM token exchange."""

    provider_id = "ibm-watsonx"

    def __init__(self, *, known_models=None, opener=urllib.request.urlopen) -> None:
        super().__init__(known_models=known_models)
        self._opener = opener
        self._api_key = str(os.environ.get("WATSONX_API_KEY") or "").strip()
        self._iam_token = str(os.environ.get("WATSONX_IAM_TOKEN") or "").strip()
        self._base_url = str(os.environ.get("WATSONX_URL") or "https://us-south.ml.cloud.ibm.com").rstrip("/")
        self._project = str(os.environ.get("WATSONX_PROJECT_ID") or "").strip()
        self._space = str(os.environ.get("WATSONX_SPACE_ID") or "").strip()
        self._version = str(os.environ.get("WATSONX_API_VERSION") or "2025-02-11")

    def _token(self) -> str:
        if self._iam_token:
            return self._iam_token
        if not self._api_key:
            raise EnterpriseProviderError("authentication_required", "watsonx API key is required")
        body = urllib.parse.urlencode({"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": self._api_key}).encode()
        request = urllib.request.Request(
            "https://iam.cloud.ibm.com/identity/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        raw = self._open(request)
        token = str(raw.get("access_token") or "")
        if not token:
            raise EnterpriseProviderError("authentication_failed", "IBM IAM token exchange failed")
        self._iam_token = token
        return token

    def _open(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise EnterpriseProviderError("provider_error", "watsonx request failed", retryable=True) from exc
        return payload if isinstance(payload, dict) else {}

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            self._base_url + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json", "Accept": "application/json"},
            method=method,
        )
        return self._open(request)

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        models: list[dict[str, Any]] = []
        path = f"/ml/v1/foundation_model_specs?version={urllib.parse.quote(self._version)}&limit=200"
        while path:
            raw = self._request("GET", path)
            for item in raw.get("resources", []) if isinstance(raw.get("resources"), list) else []:
                model_id = str(item.get("model_id") or "")
                if model_id:
                    models.append({"id": f"{self.provider_id}/{model_id}", "model_id": model_id, "display_name": str(item.get("label") or model_id), "type": "chat", "metadata": {"source": "watsonx_foundation_model_specs"}})
            next_ref = raw.get("next", {}).get("href") if isinstance(raw.get("next"), dict) else ""
            path = urllib.parse.urlsplit(str(next_ref)).path + ("?" + urllib.parse.urlsplit(str(next_ref)).query if next_ref else "") if next_ref else ""
        return models or super().list_models()

    def complete(self, model, messages, tools, params):
        if not self._project and not self._space:
            raise EnterpriseProviderError("configuration_error", "watsonx project or space is required")
        body: dict[str, Any] = {"model_id": self._model_id(model), "messages": messages, "parameters": dict(params or {})}
        body["project_id" if self._project else "space_id"] = self._project or self._space
        if tools:
            body["tools"] = tools
        raw = self._request("POST", f"/ml/v1/text/chat?version={urllib.parse.quote(self._version)}", body)
        choice = raw.get("choices", [{}])[0]
        text = str(choice.get("message", {}).get("content") or "")
        return self._standard_response(text, raw.get("usage"))


class OCIProvider(EnterpriseNativeProvider):
    """OCI Generative AI adapter using the OCI SDK configuration provider chain."""

    provider_id = "oracle-oci-generative-ai"

    def __init__(self, *, known_models=None, sdk_factory=None) -> None:
        super().__init__(known_models=known_models)
        self._sdk_factory = sdk_factory
        self._compartment = str(os.environ.get("OCI_COMPARTMENT_ID") or "").strip()

    def _clients(self):
        if self._sdk_factory is not None:
            return self._sdk_factory()
        try:
            import oci
        except ImportError as exc:
            raise self._missing_dependency("oci") from exc
        config_file = str(os.environ.get("OCI_CONFIG_FILE") or oci.config.DEFAULT_LOCATION)
        profile = str(os.environ.get("OCI_PROFILE") or "DEFAULT")
        config = oci.config.from_file(file_location=config_file, profile_name=profile)
        region = str(os.environ.get("OCI_REGION") or "").strip()
        if region:
            config["region"] = region
        return (
            oci.generative_ai.GenerativeAiClient(config),
            oci.generative_ai_inference.GenerativeAiInferenceClient(config),
            oci.generative_ai_inference.models,
        )

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        if not self._compartment:
            raise EnterpriseProviderError("configuration_error", "OCI compartment ID is required")
        control, _, _ = self._clients()
        models: list[dict[str, Any]] = []
        page = None
        while True:
            response = control.list_models(compartment_id=self._compartment, page=page)
            items = getattr(getattr(response, "data", None), "items", [])
            for item in items:
                model_id = str(getattr(item, "id", "") or "")
                capabilities = {str(value) for value in getattr(item, "capabilities", [])}
                model_type = "embedding" if "TEXT_EMBEDDINGS" in capabilities else "rerank" if "TEXT_RERANK" in capabilities else "chat"
                if model_id:
                    models.append({"id": f"{self.provider_id}/{model_id}", "model_id": model_id, "display_name": str(getattr(item, "display_name", "") or model_id), "type": model_type, "metadata": {"source": "oci_list_models"}})
            headers = getattr(response, "headers", {}) or {}
            page = headers.get("opc-next-page")
            if not page:
                break
        return models or super().list_models()

    def complete(self, model, messages, tools, params):
        if not self._compartment:
            raise EnterpriseProviderError("configuration_error", "OCI compartment ID is required")
        _, runtime, models_api = self._clients()
        serving_mode = models_api.OnDemandServingMode(model_id=self._model_id(model))
        converted = []
        for message in messages:
            content = message.get("content", "")
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            converted.append(models_api.Message(role=str(message.get("role") or "USER").upper(), content=[models_api.TextContent(text=text)]))
        chat_request = models_api.GenericChatRequest(messages=converted, **dict(params or {}))
        details = models_api.ChatDetails(compartment_id=self._compartment, serving_mode=serving_mode, chat_request=chat_request)
        response = runtime.chat(details)
        data = getattr(response, "data", response)
        chat_response = getattr(data, "chat_response", data)
        choices = getattr(chat_response, "choices", [])
        message = getattr(choices[0], "message", None) if choices else None
        content = getattr(message, "content", []) if message else []
        text = "".join(str(getattr(item, "text", "") or "") for item in content)
        return self._standard_response(text)


class SnowflakeCortexProvider(EnterpriseNativeProvider):
    """Snowflake Cortex AI through the official Python connector."""

    provider_id = "snowflake-cortex"

    def __init__(self, *, known_models=None, connector_factory=None) -> None:
        super().__init__(known_models=known_models)
        self._connector_factory = connector_factory

    def _connect(self):
        if self._connector_factory is not None:
            return self._connector_factory()
        try:
            import snowflake.connector
        except ImportError as exc:
            raise self._missing_dependency("snowflake-connector-python") from exc
        connection_name = str(os.environ.get("SNOWFLAKE_CONNECTION_NAME") or "").strip()
        if connection_name:
            return snowflake.connector.connect(connection_name=connection_name)
        kwargs = {
            key: value
            for key, env_name in {
                "account": "SNOWFLAKE_ACCOUNT",
                "user": "SNOWFLAKE_USER",
                "warehouse": "SNOWFLAKE_WAREHOUSE",
                "role": "SNOWFLAKE_ROLE",
                "authenticator": "SNOWFLAKE_AUTHENTICATOR",
                "private_key_file": "SNOWFLAKE_PRIVATE_KEY_PATH",
                "password": "SNOWFLAKE_PASSWORD",
                "token": "SNOWFLAKE_OAUTH_TOKEN",
            }.items()
            if (value := str(os.environ.get(env_name) or "").strip())
        }
        return snowflake.connector.connect(**kwargs)

    def list_models(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        if not refresh:
            return super().list_models()
        connection = self._connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute("SHOW CORTEX BASE MODELS IN SCHEMA SNOWFLAKE.MODELS")
                columns = [str(item[0]).lower() for item in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            connection.close()
        models = []
        for row in rows:
            model_id = str(row.get("name") or "")
            if model_id:
                models.append({"id": f"{self.provider_id}/{model_id}", "model_id": model_id, "display_name": model_id, "type": "chat", "metadata": {"source": "show_cortex_base_models", "lifecycle": row.get("lifecycle_status"), "available_regions": row.get("available_regions"), "legacy_date": row.get("legacy_date"), "eol_date": row.get("eol_date")}})
        return models or super().list_models()

    def complete(self, model, messages, tools, params):
        if tools:
            raise EnterpriseProviderError("unsupported_feature", "Snowflake Cortex tool calls are not mapped")
        history = [{"role": str(item.get("role") or "user"), "content": item.get("content", "")} for item in messages]
        connection = self._connect()
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(%s, PARSE_JSON(%s), PARSE_JSON(%s))",
                    (self._model_id(model), json.dumps(history), json.dumps(dict(params or {}))),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        finally:
            connection.close()
        raw = row[0] if row else ""
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            payload = raw
        if isinstance(payload, dict):
            text = str(payload.get("choices", [{}])[0].get("messages") or payload.get("response") or "")
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        else:
            text, usage = str(payload or ""), {}
        return self._standard_response(text, usage)
