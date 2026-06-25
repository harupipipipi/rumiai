from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .models import RumiTemplate, TemplateDependencySpec, TemplateDiagnostic, TemplateStatus
from .registry import TemplateRegistry


@dataclass
class TemplateActivationState:
    template_id: str
    active: bool
    projectable: bool
    dependency_ids: list[str] = field(default_factory=list)
    optional_dependency_ids: list[str] = field(default_factory=list)
    provided_capabilities: list[str] = field(default_factory=list)
    capability_providers: dict[str, list[str]] = field(default_factory=dict)
    blocked_by: list[str] = field(default_factory=list)
    diagnostics: list[TemplateDiagnostic] = field(default_factory=list)


@dataclass
class TemplateActivationPlan:
    ordered_template_ids: list[str]
    states: dict[str, TemplateActivationState]
    diagnostics: list[TemplateDiagnostic]


class TemplateActivationPlanner:
    def __init__(self, registry: TemplateRegistry) -> None:
        self._registry = registry
        self._templates = {template.id: template for template in registry.list()}

    def build(self) -> TemplateActivationPlan:
        states = {
            template_id: TemplateActivationState(
                template_id=template_id,
                active=_is_active(template),
                projectable=_is_active(template),
                dependency_ids=[spec.id for spec in template.dependencies if not spec.optional],
                optional_dependency_ids=[
                    spec.id for spec in template.dependencies if spec.optional
                ],
            )
            for template_id, template in self._templates.items()
        }
        for template_id in sorted(self._templates):
            self._diagnose_dependencies(template_id, states)
        self._diagnose_cycles(states)
        self._compute_capabilities(states)
        for template_id, state in states.items():
            if not state.active:
                state.projectable = False
            if state.blocked_by or any(diagnostic.is_error for diagnostic in state.diagnostics):
                state.projectable = False
        ordered_template_ids = self._topological_order(states)
        diagnostics = [
            diagnostic
            for template_id in sorted(states)
            for diagnostic in states[template_id].diagnostics
        ]
        return TemplateActivationPlan(
            ordered_template_ids=ordered_template_ids,
            states=states,
            diagnostics=diagnostics,
        )

    def _diagnose_dependencies(
        self,
        template_id: str,
        states: dict[str, TemplateActivationState],
    ) -> None:
        template = self._templates[template_id]
        state = states[template_id]
        if not state.active:
            state.diagnostics.append(
                _diagnostic(
                    "template.activation.inactive",
                    f"template status is not active: {_value(template.status)}",
                    template,
                    severity="info",
                    path="/status",
                )
            )
        for dependency in template.dependencies:
            self._diagnose_dependency(template, dependency, states)
        for conflict in template.conflicts:
            target = self._templates.get(conflict.id)
            if target is None or not _is_active(target):
                continue
            state.blocked_by.append(conflict.id)
            state.diagnostics.append(
                _diagnostic(
                    "template.conflict.active",
                    f"template conflicts with active template: {conflict.id}",
                    template,
                    path="/conflicts",
                )
            )

    def _diagnose_dependency(
        self,
        template: RumiTemplate,
        dependency: TemplateDependencySpec,
        states: dict[str, TemplateActivationState],
    ) -> None:
        state = states[template.id]
        target = self._templates.get(dependency.id)
        severity = "warning" if dependency.optional else "error"
        if target is None:
            if not dependency.optional:
                state.blocked_by.append(dependency.id)
            state.diagnostics.append(
                _diagnostic(
                    "template.dependency.missing",
                    f"missing template dependency: {dependency.id}",
                    template,
                    severity=severity,
                    path="/dependencies",
                )
            )
            return
        if not _is_active(target):
            if not dependency.optional:
                state.blocked_by.append(dependency.id)
            state.diagnostics.append(
                _diagnostic(
                    "template.dependency.inactive",
                    f"template dependency is not active: {dependency.id}",
                    template,
                    severity=severity,
                    path="/dependencies",
                )
            )
        mismatch_diagnostic = _version_mismatch_diagnostic(template, dependency, target)
        if mismatch_diagnostic is not None:
            mismatch_diagnostic.severity = severity
            if not dependency.optional:
                state.blocked_by.append(dependency.id)
            state.diagnostics.append(mismatch_diagnostic)

    def _diagnose_cycles(self, states: dict[str, TemplateActivationState]) -> None:
        graph = {
            template_id: sorted(
                set(_extends_list(template.extends))
                | {spec.id for spec in template.dependencies if not spec.optional}
            )
            for template_id, template in self._templates.items()
        }
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(template_id: str) -> None:
            if template_id in visited:
                return
            if template_id in visiting:
                cycle = visiting[visiting.index(template_id) :] + [template_id]
                for cycle_id in cycle:
                    if cycle_id not in states:
                        continue
                    states[cycle_id].blocked_by.extend(item for item in cycle if item != cycle_id)
                    states[cycle_id].diagnostics.append(
                        _diagnostic(
                            "template.activation.cycle",
                            f"template activation cycle: {' -> '.join(cycle)}",
                            self._templates[cycle_id],
                            path="/dependencies",
                        )
                    )
                return
            visiting.append(template_id)
            for dependency_id in graph.get(template_id, []):
                if dependency_id in self._templates:
                    visit(dependency_id)
            visiting.pop()
            visited.add(template_id)

        for template_id in sorted(self._templates):
            visit(template_id)

    def _compute_capabilities(self, states: dict[str, TemplateActivationState]) -> None:
        memo: dict[str, dict[str, set[str]]] = {}

        def closure(template_id: str, stack: set[str] | None = None) -> dict[str, set[str]]:
            if template_id in memo:
                return memo[template_id]
            stack = set(stack or set())
            if template_id in stack:
                return {}
            stack.add(template_id)
            template = self._templates[template_id]
            providers: dict[str, set[str]] = {
                capability: {template_id} for capability in template.capabilities.provides
            }
            for dependency_id in _capability_dependency_ids(template):
                target_state = states.get(dependency_id)
                if target_state is None or not target_state.active or target_state.blocked_by:
                    continue
                for capability, provider_ids in closure(dependency_id, stack).items():
                    providers.setdefault(capability, set()).update(provider_ids)
            memo[template_id] = providers
            return providers

        for template_id in sorted(self._templates):
            template = self._templates[template_id]
            state = states[template_id]
            providers = closure(template_id)
            state.provided_capabilities = sorted(providers)
            state.capability_providers = {
                capability: sorted(provider_ids)
                for capability, provider_ids in sorted(providers.items())
            }
            missing = [
                capability
                for capability in template.capabilities.requires
                if capability not in providers
            ]
            if missing:
                state.blocked_by.extend(missing)
                for capability in missing:
                    state.diagnostics.append(
                        _diagnostic(
                            "template.capability.missing",
                            f"missing required capability: {capability}",
                            template,
                            path="/capabilities/requires",
                        )
                    )

    def _topological_order(self, states: dict[str, TemplateActivationState]) -> list[str]:
        dependencies = {
            template_id: sorted(
                dependency_id
                for dependency_id in _activation_dependency_ids(template)
                if dependency_id in self._templates
            )
            for template_id, template in self._templates.items()
        }
        dependents: dict[str, set[str]] = {template_id: set() for template_id in self._templates}
        remaining_counts: dict[str, int] = {}
        for template_id, dependency_ids in dependencies.items():
            unique_dependency_ids = set(dependency_ids)
            remaining_counts[template_id] = len(unique_dependency_ids)
            for dependency_id in unique_dependency_ids:
                dependents.setdefault(dependency_id, set()).add(template_id)
        ready = sorted(template_id for template_id, count in remaining_counts.items() if count == 0)
        ordered: list[str] = []
        while ready:
            current = ready.pop(0)
            ordered.append(current)
            for dependent in sorted(dependents.get(current, set())):
                remaining_counts[dependent] -= 1
                if remaining_counts[dependent] == 0:
                    ready.append(dependent)
                    ready.sort()
        leftovers = sorted(
            template_id for template_id in self._templates if template_id not in ordered
        )
        return [*ordered, *leftovers]


def _version_mismatch_diagnostic(
    template: RumiTemplate,
    dependency: TemplateDependencySpec,
    target: RumiTemplate,
) -> TemplateDiagnostic | None:
    if dependency.version is None:
        return None
    try:
        specifier = SpecifierSet(str(dependency.version))
    except InvalidSpecifier:
        return _diagnostic(
            "template.dependency.invalid_version_specifier",
            f"invalid dependency version specifier: {dependency.version}",
            template,
            path="/dependencies",
        )
    try:
        target_version = Version(str(target.version))
    except InvalidVersion:
        return _diagnostic(
            "template.version.invalid",
            f"dependency target version is invalid: {target.version}",
            template,
            path="/dependencies",
        )
    if target_version in specifier:
        return None
    return _diagnostic(
        "template.dependency.version_mismatch",
        (
            f"template dependency version mismatch: {dependency.id} "
            f"{target.version} does not satisfy {dependency.version}"
        ),
        template,
        path="/dependencies",
    )


def _activation_dependency_ids(template: RumiTemplate) -> list[str]:
    return sorted(
        set(_extends_list(template.extends))
        | {spec.id for spec in template.dependencies if spec.id and not spec.optional}
    )


def _capability_dependency_ids(template: RumiTemplate) -> list[str]:
    return sorted(
        set(_activation_dependency_ids(template))
        | {spec.id for spec in template.dependencies if spec.id and spec.optional}
    )


def _extends_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _is_active(template: RumiTemplate) -> bool:
    return _value(template.status) == TemplateStatus.ACTIVE.value


def _diagnostic(
    code: str,
    message: str,
    template: RumiTemplate,
    *,
    severity: str = "error",
    path: str | None = None,
) -> TemplateDiagnostic:
    return TemplateDiagnostic(
        code=code,
        message=message,
        severity=severity,
        template_id=template.id,
        path=path,
        source_path=str(template.source_path) if template.source_path else None,
    )


def _value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)
