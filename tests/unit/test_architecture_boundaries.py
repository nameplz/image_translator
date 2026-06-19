from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "image_translator"
PACKAGE_NAME = "image_translator"

EXPECTED_LAYERS = (
    "app",
    "config",
    "domain",
    "providers",
    "services",
    "workflows",
    "use_cases",
    "persistence",
    "gui",
    "observability",
)

DOMAIN_ALLOWED_EXTERNAL_ROOTS = {"pydantic"}
DOMAIN_FORBIDDEN_ROOTS = {
    "PySide6",
    "cv2",
    "deepl",
    "google",
    "groq",
    "langchain",
    "langgraph",
    "openai",
    "xai",
}
GUI_ALLOWED_INTERNAL_PREFIXES = (
    "image_translator.config",
    "image_translator.domain",
    "image_translator.gui",
    "image_translator.use_cases",
)


def _iter_python_files(layer: str) -> tuple[Path, ...]:
    layer_root = PACKAGE_ROOT / layer
    return tuple(sorted(layer_root.rglob("*.py")))


def _module_name(path: Path) -> str:
    relative_path = path.relative_to(PACKAGE_ROOT).with_suffix("")
    if relative_path.name == "__init__":
        relative_path = relative_path.parent
    return ".".join((PACKAGE_NAME, *relative_path.parts))


def _resolve_from_import(module_name: str, node: ast.ImportFrom, *, is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""

    package_parts = module_name.split(".") if is_package else module_name.split(".")[:-1]
    parent_count = node.level - 1

    if parent_count > len(package_parts):
        return node.module or ""

    base_parts = package_parts[: len(package_parts) - parent_count]
    if node.module:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts)


def _imported_modules(path: Path) -> tuple[str, ...]:
    module_name = _module_name(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(
                _resolve_from_import(module_name, node, is_package=path.name == "__init__.py")
            )

    return tuple(import_name for import_name in imports if import_name)


def _root_name(import_name: str) -> str:
    return import_name.split(".", maxsplit=1)[0]


def test_declared_package_layers_exist_and_are_importable() -> None:
    for layer in EXPECTED_LAYERS:
        layer_root = PACKAGE_ROOT / layer

        assert layer_root.is_dir(), f"Missing package layer directory: {layer}"
        assert (layer_root / "__init__.py").is_file(), f"Missing package marker: {layer}"
        importlib.import_module(f"{PACKAGE_NAME}.{layer}")


def test_domain_only_depends_on_stdlib_pydantic_and_domain_modules() -> None:
    for path in _iter_python_files("domain"):
        for import_name in _imported_modules(path):
            root_name = _root_name(import_name)

            assert root_name not in DOMAIN_FORBIDDEN_ROOTS, (
                f"{path.relative_to(ROOT)} imports forbidden domain dependency {import_name!r}"
            )
            assert (
                import_name.startswith("image_translator.domain")
                or root_name in DOMAIN_ALLOWED_EXTERNAL_ROOTS
                or root_name in sys.stdlib_module_names
            ), f"{path.relative_to(ROOT)} imports non-domain dependency {import_name!r}"


def test_services_do_not_import_provider_layer() -> None:
    for path in _iter_python_files("services"):
        provider_imports = [
            import_name
            for import_name in _imported_modules(path)
            if import_name == "image_translator.providers"
            or import_name.startswith("image_translator.providers.")
        ]

        assert not provider_imports, (
            f"{path.relative_to(ROOT)} imports provider layer directly: {provider_imports}"
        )


def test_use_cases_do_not_import_provider_layer() -> None:
    for path in _iter_python_files("use_cases"):
        provider_imports = [
            import_name
            for import_name in _imported_modules(path)
            if import_name == "image_translator.providers"
            or import_name.startswith("image_translator.providers.")
        ]

        assert not provider_imports, (
            f"{path.relative_to(ROOT)} imports provider layer directly: {provider_imports}"
        )


def test_gui_imports_do_not_bypass_use_cases() -> None:
    for path in _iter_python_files("gui"):
        bypass_imports = [
            import_name
            for import_name in _imported_modules(path)
            if import_name.startswith("image_translator.")
            and import_name != "image_translator"
            and not import_name.startswith(GUI_ALLOWED_INTERNAL_PREFIXES)
        ]

        assert not bypass_imports, (
            f"{path.relative_to(ROOT)} imports application internals directly: {bypass_imports}"
        )
