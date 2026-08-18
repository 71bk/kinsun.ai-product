"""Static import-boundary checks for the Python components.

These tests intentionally use only the standard library.  They inspect source
syntax without importing application modules, so they cannot require a database,
provider credentials, or another component's virtual environment.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Component:
    name: str
    package: str
    package_root: Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
COMPONENTS = (
    Component("core-api", "app", REPOSITORY_ROOT / "services" / "core-api" / "app"),
    Component(
        "agent-runtime",
        "agent_runtime",
        REPOSITORY_ROOT / "services" / "agent-runtime" / "src" / "agent_runtime",
    ),
    Component(
        "rag-ingestion",
        "rag_ingestion",
        REPOSITORY_ROOT / "services" / "rag-ingestion" / "src" / "rag_ingestion",
    ),
    Component(
        "speech-gateway",
        "speech_gateway",
        REPOSITORY_ROOT / "services" / "speech-gateway" / "src" / "speech_gateway",
    ),
)
CORE = COMPONENTS[0]
COMPONENT_BY_PACKAGE = {component.package: component for component in COMPONENTS}


def _python_files(component: Component) -> list[Path]:
    assert (
        component.package_root.is_dir()
    ), f"Python source root is missing for {component.name}: {component.package_root}"
    return sorted(component.package_root.rglob("*.py"))


def _module_name(component: Component, source_file: Path) -> str:
    relative_path = source_file.relative_to(component.package_root)
    relative_parts = list(relative_path.parts)
    if relative_parts[-1] == "__init__.py":
        relative_parts.pop()
    else:
        relative_parts[-1] = source_file.stem
    return ".".join((component.package, *relative_parts))


def _module_inventory(component: Component) -> dict[str, Path]:
    return {
        _module_name(component, source_file): source_file
        for source_file in _python_files(component)
    }


def _parse(source_file: Path) -> ast.Module:
    return ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))


def _absolute_import_roots(tree: ast.Module) -> Iterable[tuple[int, str]]:
    """Yield line number and top-level package for absolute imports."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                yield node.lineno, imported.name.partition(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.partition(".")[0]


def _current_package(module_name: str, source_file: Path) -> list[str]:
    parts = module_name.split(".")
    return parts if source_file.name == "__init__.py" else parts[:-1]


def _from_import_base(
    node: ast.ImportFrom,
    *,
    module_name: str,
    source_file: Path,
) -> str | None:
    if node.level == 0:
        return node.module

    package_parts = _current_package(module_name, source_file)
    parents_to_remove = node.level - 1
    if parents_to_remove >= len(package_parts):
        return None

    anchor = package_parts[: len(package_parts) - parents_to_remove]
    if node.module:
        anchor.extend(node.module.split("."))
    return ".".join(anchor)


def _import_targets(
    node: ast.Import | ast.ImportFrom,
    *,
    module_name: str,
    source_file: Path,
) -> Iterable[str]:
    """Yield possible imported modules, resolving relative-import syntax."""
    if isinstance(node, ast.Import):
        yield from (imported.name for imported in node.names)
        return

    base = _from_import_base(node, module_name=module_name, source_file=source_file)
    if not base:
        return
    yield base
    for imported in node.names:
        if imported.name != "*":
            yield f"{base}.{imported.name}"


def _resolve_known_module(target: str, known_modules: set[str]) -> str | None:
    """Resolve a module or imported attribute to its longest known module prefix."""
    candidate = target
    while candidate:
        if candidate in known_modules:
            return candidate
        candidate = candidate.rpartition(".")[0]
    return None


def _import_graph(component: Component) -> dict[str, set[str]]:
    modules = _module_inventory(component)
    known_modules = set(modules)
    graph = {module_name: set() for module_name in modules}

    for module_name, source_file in modules.items():
        for node in ast.walk(_parse(source_file)):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            for target in _import_targets(
                node,
                module_name=module_name,
                source_file=source_file,
            ):
                dependency = _resolve_known_module(target, known_modules)
                if dependency is not None and dependency != module_name:
                    graph[module_name].add(dependency)
    return graph


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    """Return deterministic multi-node SCCs using Tarjan's algorithm."""
    next_index = 0
    indexes: dict[str, int] = {}
    low_links: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(module_name: str) -> None:
        nonlocal next_index
        indexes[module_name] = next_index
        low_links[module_name] = next_index
        next_index += 1
        stack.append(module_name)
        on_stack.add(module_name)

        for dependency in sorted(graph[module_name]):
            if dependency not in indexes:
                visit(dependency)
                low_links[module_name] = min(low_links[module_name], low_links[dependency])
            elif dependency in on_stack:
                low_links[module_name] = min(low_links[module_name], indexes[dependency])

        if low_links[module_name] != indexes[module_name]:
            return

        connected: list[str] = []
        while True:
            dependency = stack.pop()
            on_stack.remove(dependency)
            connected.append(dependency)
            if dependency == module_name:
                break
        if len(connected) > 1:
            components.append(tuple(sorted(connected)))

    for module_name in sorted(graph):
        if module_name not in indexes:
            visit(module_name)
    return sorted(components)


def _repository_relative(source_file: Path) -> str:
    return source_file.relative_to(REPOSITORY_ROOT).as_posix()


def test_python_components_do_not_import_each_other_directly() -> None:
    violations: list[str] = []

    for source_component in COMPONENTS:
        for source_file in _python_files(source_component):
            for line_number, imported_package in _absolute_import_roots(_parse(source_file)):
                target_component = COMPONENT_BY_PACKAGE.get(imported_package)
                if target_component is None or target_component == source_component:
                    continue
                violations.append(
                    f"{_repository_relative(source_file)}:{line_number}: "
                    f"{source_component.name} imports {target_component.name} "
                    f"through {imported_package!r}"
                )

    assert not violations, "Direct cross-component Python imports found:\n" + "\n".join(
        sorted(violations)
    )


def test_core_import_graph_has_no_multi_module_cycles() -> None:
    cycles = _strongly_connected_components(_import_graph(CORE))

    formatted_cycles = "\n".join(f"- {', '.join(cycle)}" for cycle in cycles)
    assert not cycles, f"Core multi-module import cycles found:\n{formatted_cycles}"


def test_core_application_services_do_not_import_outer_layers() -> None:
    """Keep business services independent of HTTP and concrete adapter layers."""
    modules = _module_inventory(CORE)
    violations: set[str] = set()

    for module_name, source_file in modules.items():
        if module_name != "app.services" and not module_name.startswith("app.services."):
            continue
        # This legacy-named module is the explicit composition root for provider clients.
        if module_name == "app.services.service_dependencies":
            continue
        for node in ast.walk(_parse(source_file)):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            targets = tuple(
                _import_targets(
                    node,
                    module_name=module_name,
                    source_file=source_file,
                )
            )
            if any(
                target == forbidden_prefix or target.startswith(f"{forbidden_prefix}.")
                for target in targets
                for forbidden_prefix in ("app.adapters", "app.api", "app.middleware")
            ):
                violations.add(f"{_repository_relative(source_file)}:{node.lineno}: {module_name}")

    assert not violations, "Core services import outer layers:\n" + "\n".join(sorted(violations))


def test_core_and_domain_packages_only_depend_on_inward_packages() -> None:
    """Keep framework, persistence, transport, and service code out of inward packages."""
    modules = _module_inventory(CORE)
    violations: set[str] = set()
    inward_prefixes = ("app.core", "app.domain")

    for module_name, source_file in modules.items():
        if not any(
            module_name == prefix or module_name.startswith(f"{prefix}.")
            for prefix in inward_prefixes
        ):
            continue
        for node in ast.walk(_parse(source_file)):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            targets = tuple(
                _import_targets(
                    node,
                    module_name=module_name,
                    source_file=source_file,
                )
            )
            for target in targets:
                if not (target == "app" or target.startswith("app.")):
                    continue
                if any(
                    target == prefix or target.startswith(f"{prefix}.")
                    for prefix in inward_prefixes
                ):
                    continue
                violations.add(
                    f"{_repository_relative(source_file)}:{node.lineno}: "
                    f"{module_name} imports {target}"
                )

    assert not violations, "Inward packages import outer packages:\n" + "\n".join(
        sorted(violations)
    )
