"""Import-boundary rules from AGENTS.md / architecture_v0.1.md, enforced
mechanically. These are the properties that make "the bot can create
leads/orders but never read them back, and never write settings" true by
construction rather than by convention."""

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[2] / "src" / "app"

# the bot's whole request path
BOT_MODULES = [
    APP_ROOT / "api" / "bot" / "router.py",
    APP_ROOT / "services" / "bot_engine.py",
    APP_ROOT / "services" / "bot_tools.py",
]

SETTINGS_WRITE_MODULES = {"app.repos.settings", "app.repos.settings_admin"}


def _imported_modules(path: Path) -> set[str]:
    """Fully-qualified module names a file imports, including
    `from app.repos import leads_admin` (-> app.repos.leads_admin)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _app_module_path(module: str) -> Path | None:
    if not module.startswith("app."):
        return None
    base = APP_ROOT.joinpath(*module.split(".")[1:])
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.exists():
            return candidate
    return None


def _transitive_app_imports(start: Path) -> set[str]:
    """Every app module reachable from `start` by imports."""
    seen_files: set[Path] = set()
    found: set[str] = set()
    stack = [start]
    while stack:
        path = stack.pop()
        if path in seen_files:
            continue
        seen_files.add(path)
        for module in _imported_modules(path):
            target = _app_module_path(module)
            if target is not None:
                found.add(module)
                stack.append(target)
    return found


@pytest.mark.parametrize("path", BOT_MODULES, ids=lambda p: p.name)
def test_bot_path_never_imports_admin_repos(path: Path) -> None:
    offenders = {m for m in _transitive_app_imports(path) if m.endswith("_admin")}
    assert not offenders, f"{path.name} reaches admin-only modules: {sorted(offenders)}"


@pytest.mark.parametrize("path", BOT_MODULES, ids=lambda p: p.name)
def test_bot_path_never_imports_settings_write_modules(path: Path) -> None:
    offenders = _transitive_app_imports(path) & SETTINGS_WRITE_MODULES
    assert not offenders, f"{path.name} reaches settings write modules: {sorted(offenders)}"


def test_settings_resolver_reads_through_read_only_repo() -> None:
    imports = _imported_modules(APP_ROOT / "services" / "settings_resolver.py")
    assert "app.repos.settings_read" in imports
    assert not imports & SETTINGS_WRITE_MODULES


def test_repos_filter_tenant_rows_through_tenant_scope() -> None:
    """A bare `.tenant_id == x` in a repo query skips the suspended-tenant
    check inside tenant_scope(). The listed exceptions are the deliberate,
    documented superadmin paths that are not tenant-scoped."""
    allowed = {
        "settings_admin.py",  # superadmin manages any tenant, suspended or not
        "tenants.py",  # api-key listing/revocation is a superadmin surface
        "tenant_scope.py",  # the helper itself
    }
    offenders = []
    for path in (APP_ROOT / "repos").glob("*.py"):
        if path.name in allowed:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ".tenant_id ==" in line and "tenant_scope(" not in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "bare tenant_id filters found:\n" + "\n".join(offenders)
