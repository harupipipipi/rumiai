from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TemplateContractAssertionResult:
    contract_id: str
    assertion_type: str
    passed: bool
    message: str
    severity: str = "error"
    assertion: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "assertion_type": self.assertion_type,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "assertion": dict(self.assertion),
        }


@dataclass
class TemplateContractRunResult:
    results: list[TemplateContractAssertionResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(not result.passed and result.severity == "error" for result in self.results)

    @property
    def failures(self) -> list[TemplateContractAssertionResult]:
        return [
            result for result in self.results if not result.passed and result.severity == "error"
        ]

    @property
    def warnings(self) -> list[TemplateContractAssertionResult]:
        return [result for result in self.results if result.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
            "failures": [result.to_dict() for result in self.failures],
            "warnings": [result.to_dict() for result in self.warnings],
        }


def run_template_contracts(
    catalog: dict[str, Any],
    *,
    routes: list[Any] | None = None,
    functions: dict[str, Any] | None = None,
    defaultspack_root: str | Path | None = None,
) -> TemplateContractRunResult:
    if routes is None:
        routes = _template_routes(defaultspack_root)
    if functions is None:
        functions = _template_functions(defaultspack_root)
    runner = _ContractRunner(catalog=catalog, routes=routes, functions=functions)
    return runner.run()


class _ContractRunner:
    def __init__(
        self,
        *,
        catalog: dict[str, Any],
        routes: list[Any],
        functions: dict[str, Any],
    ) -> None:
        self.catalog = catalog if isinstance(catalog, dict) else {}
        self.routes = routes
        self.functions = functions if isinstance(functions, dict) else {}

    def run(self) -> TemplateContractRunResult:
        result = TemplateContractRunResult()
        contracts = self.catalog.get("test_contracts")
        if not isinstance(contracts, list):
            return result
        for contract in contracts:
            if not isinstance(contract, dict):
                continue
            contract_id = str(contract.get("contract_id") or contract.get("id") or "").strip()
            assertions = contract.get("assertions")
            if not isinstance(assertions, list):
                continue
            for assertion in assertions:
                result.results.append(self._evaluate(contract_id, assertion))
        return result

    def _evaluate(
        self,
        contract_id: str,
        assertion: Any,
    ) -> TemplateContractAssertionResult:
        if isinstance(assertion, str):
            return TemplateContractAssertionResult(
                contract_id=contract_id,
                assertion_type="legacy_string",
                passed=True,
                severity="warning",
                message="legacy string assertions are documentation-only and should be migrated",
                assertion={"text": assertion},
            )
        if not isinstance(assertion, dict):
            return _failure(contract_id, "malformed", "assertion must be an object", {})
        assertion_type = str(assertion.get("type") or "").strip()
        if assertion_type == "catalog_contains":
            return self._catalog_contains(contract_id, assertion, expected=True)
        if assertion_type == "catalog_excludes":
            return self._catalog_contains(contract_id, assertion, expected=False)
        if assertion_type == "route_resolves":
            return self._route(contract_id, assertion, expected=True)
        if assertion_type == "route_absent":
            return self._route(contract_id, assertion, expected=False)
        if assertion_type == "function_registered":
            return self._function(contract_id, assertion, expected=True)
        if assertion_type == "function_absent":
            return self._function(contract_id, assertion, expected=False)
        if assertion_type == "permission_declared":
            return self._permission(contract_id, assertion)
        if assertion_type == "setting_field_exists":
            return self._setting_field_exists(contract_id, assertion)
        if assertion_type == "tool_policy_resolves":
            return self._tool_policy_resolves(contract_id, assertion)
        if assertion_type == "diagnostic_absent":
            return self._diagnostic_absent(contract_id, assertion)
        if assertion_type == "template_projectable":
            return self._template_projectability(contract_id, assertion, expected=True)
        if assertion_type == "template_not_projectable":
            return self._template_projectability(contract_id, assertion, expected=False)
        return _failure(
            contract_id,
            assertion_type or "unknown",
            f"unknown template contract assertion type: {assertion_type}",
            assertion,
        )

    def _catalog_contains(
        self,
        contract_id: str,
        assertion: dict[str, Any],
        *,
        expected: bool,
    ) -> TemplateContractAssertionResult:
        bucket = str(assertion.get("bucket") or "").strip()
        match = assertion.get("match")
        items = self.catalog.get(bucket)
        found = isinstance(items, list) and any(
            _matches(item, match) for item in items if isinstance(item, dict)
        )
        passed = found is expected
        kind = "catalog_contains" if expected else "catalog_excludes"
        return _result(
            contract_id,
            kind,
            passed,
            f"catalog bucket {bucket} {'contains' if expected else 'excludes'} requested item",
            assertion,
        )

    def _route(
        self,
        contract_id: str,
        assertion: dict[str, Any],
        *,
        expected: bool,
    ) -> TemplateContractAssertionResult:
        method = str(assertion.get("method") or "").strip().upper()
        path = str(assertion.get("path") or assertion.get("pattern") or "").strip()
        found = any(_route_matches(route, method, path) for route in self.routes)
        passed = found is expected
        kind = "route_resolves" if expected else "route_absent"
        return _result(
            contract_id,
            kind,
            passed,
            f"route {method} {path} {'resolves' if expected else 'is absent'}",
            assertion,
        )

    def _function(
        self,
        contract_id: str,
        assertion: dict[str, Any],
        *,
        expected: bool,
    ) -> TemplateContractAssertionResult:
        function_id = str(assertion.get("function_id") or assertion.get("id") or "").strip()
        found = function_id in self.functions
        passed = found is expected
        kind = "function_registered" if expected else "function_absent"
        return _result(
            contract_id,
            kind,
            passed,
            f"function {function_id} {'is registered' if expected else 'is absent'}",
            assertion,
        )

    def _permission(
        self,
        contract_id: str,
        assertion: dict[str, Any],
    ) -> TemplateContractAssertionResult:
        permission_id = str(assertion.get("permission_id") or assertion.get("id") or "").strip()
        found = any(
            str(item.get("permission_id") or item.get("id") or "").strip() == permission_id
            for item in self.catalog.get("permissions", [])
            if isinstance(item, dict)
        )
        return _result(
            contract_id,
            "permission_declared",
            found,
            f"permission {permission_id} is declared",
            assertion,
        )

    def _setting_field_exists(
        self,
        contract_id: str,
        assertion: dict[str, Any],
    ) -> TemplateContractAssertionResult:
        section_id = str(assertion.get("section_id") or "").strip()
        field_id = str(assertion.get("field_id") or assertion.get("id") or "").strip()
        field_type = str(assertion.get("field_type") or assertion.get("type") or "").strip()
        found = False
        for section in self.catalog.get("settings_sections", []):
            if not isinstance(section, dict):
                continue
            if section_id and str(section.get("id") or "").strip() != section_id:
                continue
            fields = section.get("fields")
            if not isinstance(fields, list):
                continue
            for settings_field in fields:
                if not isinstance(settings_field, dict):
                    continue
                if field_id and str(settings_field.get("id") or "").strip() != field_id:
                    continue
                if field_type and str(settings_field.get("type") or "").strip() != field_type:
                    continue
                found = True
                break
        return _result(
            contract_id,
            "setting_field_exists",
            found,
            f"setting field {section_id}/{field_id or field_type} exists",
            assertion,
        )

    def _tool_policy_resolves(
        self,
        contract_id: str,
        assertion: dict[str, Any],
    ) -> TemplateContractAssertionResult:
        policy_id = str(assertion.get("policy_id") or assertion.get("id") or "").strip()
        try:
            from .tool_policy_resolution import resolve_template_tool_policy

            resolution = resolve_template_tool_policy(
                {"template_tool_policy_id": policy_id},
                catalog=self.catalog,
            )
            passed = bool(resolution.applied and not resolution.blocked)
        except Exception:
            passed = False
        return _result(
            contract_id,
            "tool_policy_resolves",
            passed,
            f"tool policy {policy_id} resolves",
            assertion,
        )

    def _diagnostic_absent(
        self,
        contract_id: str,
        assertion: dict[str, Any],
    ) -> TemplateContractAssertionResult:
        code = str(assertion.get("code") or "").strip()
        severity = str(assertion.get("severity") or "").strip()
        found = False
        for diagnostic in self.catalog.get("template_diagnostics", []):
            if not isinstance(diagnostic, dict):
                continue
            if code and str(diagnostic.get("code") or "").strip() != code:
                continue
            if severity and str(diagnostic.get("severity") or "").strip() != severity:
                continue
            found = True
            break
        return _result(
            contract_id,
            "diagnostic_absent",
            not found,
            f"diagnostic {code or severity or '*'} is absent",
            assertion,
        )

    def _template_projectability(
        self,
        contract_id: str,
        assertion: dict[str, Any],
        *,
        expected: bool,
    ) -> TemplateContractAssertionResult:
        template_id = str(assertion.get("template_id") or assertion.get("id") or "").strip()
        summary = next(
            (
                item
                for item in self.catalog.get("templates", [])
                if isinstance(item, dict) and str(item.get("id") or "").strip() == template_id
            ),
            None,
        )
        projectable = bool(summary and summary.get("projectable"))
        kind = "template_projectable" if expected else "template_not_projectable"
        return _result(
            contract_id,
            kind,
            projectable is expected,
            f"template {template_id} projectable={expected}",
            assertion,
        )


def _result(
    contract_id: str,
    assertion_type: str,
    passed: bool,
    message: str,
    assertion: dict[str, Any],
) -> TemplateContractAssertionResult:
    return TemplateContractAssertionResult(
        contract_id=contract_id,
        assertion_type=assertion_type,
        passed=passed,
        message=message,
        assertion=dict(assertion),
    )


def _failure(
    contract_id: str,
    assertion_type: str,
    message: str,
    assertion: dict[str, Any],
) -> TemplateContractAssertionResult:
    return TemplateContractAssertionResult(
        contract_id=contract_id,
        assertion_type=assertion_type,
        passed=False,
        message=message,
        assertion=dict(assertion),
    )


def _matches(item: Any, expected: Any) -> bool:
    if not isinstance(expected, dict):
        return item == expected
    if not isinstance(item, dict):
        return False
    for key, expected_value in expected.items():
        if key not in item:
            return False
        actual = item.get(key)
        if isinstance(expected_value, dict):
            if not _matches(actual, expected_value):
                return False
            continue
        if isinstance(actual, list) and not isinstance(expected_value, list):
            if expected_value not in actual:
                return False
            continue
        if actual != expected_value:
            return False
    return True


def _route_matches(route: Any, method: str, path: str) -> bool:
    if isinstance(route, dict):
        route_method = str(route.get("method") or "").strip().upper()
        route_path = str(route.get("path") or route.get("pattern") or "").strip()
    else:
        route_method = str(getattr(route, "method", "") or "").strip().upper()
        route_path = str(getattr(route, "pattern", "") or getattr(route, "path", "") or "").strip()
    return route_method == method and route_path == path


def _template_routes(defaultspack_root: str | Path | None) -> list[Any]:
    try:
        from ecosystem.defaultspack.transport.registry import template_http_route_specs

        return list(template_http_route_specs(defaultspack_root=defaultspack_root))
    except Exception:
        return []


def _template_functions(defaultspack_root: str | Path | None) -> dict[str, Any]:
    try:
        template_specs = importlib.import_module("domain.function_runtime.template_specs")
        return template_specs.template_function_specs(defaultspack_root)
    except Exception:
        return {}
