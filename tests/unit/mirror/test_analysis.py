"""Phase 2: source-mirror identity, Python symbols, imports and safe discovery."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from matma.analysis import inspect_project
from matma.analysis.paths import mirror_paths, module_name
from matma.cli import main


def write(project: Path, name: str, contents: str) -> Path:
    p = project / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(contents, encoding="utf-8")
    return p


def inspection(root: Path, **kwargs: object) -> dict:
    return inspect_project(project_root=root, **kwargs)


def test_module_as_atomic_mirror_for_many_classes_functions_and_methods(tmp_path: Path) -> None:
    write(tmp_path, "src/acme/__init__.py", "")
    write(tmp_path, "src/acme/pricing.py", '''
import math

def discount(price):
    def internal(x):
        return x
    return internal(price)

async def async_discount(price):
    return price

class A:
    def price(self):
        return 10

    async def calculate(self):
        return 11

class B(A):
    pass
''')
    result = inspection(tmp_path)
    assert result["summary"]["source_files"] == 2
    assert result["summary"]["testable_modules"] == 1
    assert result["summary"]["diagnostic_errors"] == 0
    module = result["files"][1]
    assert module["source_file"] == "src/acme/pricing.py"
    assert module["module_name"] == "acme.pricing"
    assert {(x["qualname"], x["kind"]) for x in module["symbols"]} == {
        ("discount", "function"), ("discount.internal", "nested_function"),
        ("async_discount", "async_function"), ("A", "class"),
        ("A.price", "method"), ("A.calculate", "async_method"), ("B", "class"),
    }
    assert module["mirrors"] == {
        "unit_test": "tests/unit/mirror/src/acme/test_pricing.py",
        "interaction_test": "tests/interaction/mirror/src/acme/test_pricing_interaction.py",
        "mock_file": "tests/mocks/mirror/src/acme/mock_pricing.py",
        "manifest": "tests/mirror/src/acme/pricing.auto.yaml",
    }
    assert result["files"][0]["mirrors"]["unit_test"] is None
    assert result["symbol_to_source"]["acme.pricing.A.price"] == "src/acme/pricing.py"
    assert any(x["kind"] == "inheritance" and x["name"] == "A" for x in module["references"])


def test_package_import_alias_and_reexport_resolution(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "from .service import Worker as PublicWorker\n__all__ = ['PublicWorker']\n")
    write(tmp_path, "src/pkg/service.py", "class Worker: ...\n")
    write(tmp_path, "src/pkg/consumer.py", "from pkg import PublicWorker as W\n\ndef go():\n    return W()\n")
    result = inspection(tmp_path)
    imports = next(f for f in result["files"] if f["module_name"] == "pkg.consumer")["imports"]
    assert imports[0]["resolution"] == "internal"
    assert imports[0]["bound_name"] == "W"
    assert imports[0]["resolved_module"] == "pkg.service"
    assert imports[0]["resolved_symbol"] == "pkg.service.Worker"
    package = next(f for f in result["files"] if f["module_name"] == "pkg")
    assert package["explicit_exports"] == ["PublicWorker"]
    assert package["reexports"][0]["symbol"] == "pkg.service.Worker"
    assert package["testable"] is False


def test_import_only_is_recorded_and_type_checking_is_distinguished(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/service.py", "class Worker: ...\n")
    write(tmp_path, "src/pkg/consumer.py", '''
import pkg.service
from typing import TYPE_CHECKING as TC
import typing as typ
if TC:
    from .service import Worker as W
if typ.TYPE_CHECKING:
    from .service import Worker as U
else:
    from .service import Worker as V
''')
    result = inspection(tmp_path)
    imports = next(f for f in result["files"] if f["module_name"] == "pkg.consumer")["imports"]
    assert imports[0]["resolution"] == "internal"
    assert imports[0]["resolved_source"] == "src/pkg/service.py"
    assert {x["bound_name"]: x["type_only"] for x in imports if x["bound_name"] in {"W", "U", "V"}} == {
        "W": True, "U": True, "V": False,
    }


def test_relative_imports_resolve_without_executing_project(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/data.py", "VALUE = 3\n")
    write(tmp_path, "src/pkg/deep/__init__.py", "")
    write(tmp_path, "src/pkg/deep/consumer.py", "from .. import data as my_data\n\nraise RuntimeError('MUST NOT EXECUTE')\n")
    result = inspection(tmp_path)
    assert result["summary"]["diagnostic_errors"] == 0
    entry = next(f for f in result["files"] if f["module_name"] == "pkg.deep.consumer")
    assert entry["imports"][0]["absolute_module"] == "pkg"
    assert entry["imports"][0]["resolved_source"] == "src/pkg/data.py"
    assert entry["imports"][0]["resolved_module"] == "pkg.data"


def test_ambiguous_same_module_identity_reports_error(tmp_path: Path) -> None:
    write(tmp_path, "src/foo.py", "class Foo: pass\n")
    write(tmp_path, "src/foo/__init__.py", "class FooPkg: pass\n")
    result = inspection(tmp_path)
    assert "module_collision" in {d["code"] for d in result["diagnostics"]}
    assert "foo" not in result["module_to_source"]


def test_multi_root_discovery_and_relative_path_identity(tmp_path: Path) -> None:
    write(tmp_path, "src/a/__init__.py", "")
    write(tmp_path, "src/a/pricing.py", "def price(): return 1\n")
    write(tmp_path, "modules/b/__init__.py", "")
    write(tmp_path, "modules/b/pricing.py", "def price(): return 2\n")
    result = inspection(tmp_path, source_root="src", extra_source_roots=("modules",), explicitly_selected=True)
    assert result["summary"]["source_roots"] == ["modules", "src"]
    paths = {f["mirrors"]["unit_test"] for f in result["files"] if f["testable"]}
    assert paths == {
        "tests/unit/mirror/src/a/test_pricing.py",
        "tests/unit/mirror/modules/b/test_pricing.py",
    }
    assert result["summary"]["diagnostic_errors"] == 0


def test_multi_root_module_name_collision_is_diagnosed(tmp_path: Path) -> None:
    write(tmp_path, "src/a/pricing.py", "def price(): return 1\n")
    write(tmp_path, "plugins/a/pricing.py", "def price(): return 2\n")
    result = inspection(tmp_path, source_root="src", extra_source_roots=("plugins",), explicitly_selected=True)
    assert any(d["code"] == "module_collision" for d in result["diagnostics"])
    assert len([f for f in result["files"] if f["module_name"] == "a.pricing"]) == 2


def test_flat_layout_discovered_when_src_absent(tmp_path: Path) -> None:
    write(tmp_path, "myapp/__init__.py", "")
    write(tmp_path, "myapp/service.py", "def process(): ...\n")
    result = inspection(tmp_path)
    assert result["summary"]["source_roots"] == ["."]
    assert result["module_to_source"]["myapp.service"] == "myapp/service.py"
    assert result["files"][1]["mirrors"]["unit_test"] == "tests/unit/mirror/myapp/test_service.py"


def test_custom_pyproject_matma_roots(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[tool.matma]\nsource_roots=['source_code', 'addons']\n")
    write(tmp_path, "source_code/apkg.py", "class A: ...\n")
    write(tmp_path, "addons/bpkg.py", "class B: ...\n")
    result = inspection(tmp_path)
    assert result["summary"]["source_roots"] == ["addons", "source_code"]
    assert result["module_to_source"]["apkg"] == "source_code/apkg.py"


def test_explicit_root_overrides_pyproject(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[tool.matma]\nsource_roots=['source_code']\n")
    write(tmp_path, "source_code/hidden.py", "class Hidden: ...\n")
    write(tmp_path, "app/visible.py", "class Visible: ...\n")
    result = inspection(tmp_path, source_root="app", explicitly_selected=True)
    assert result["summary"]["source_roots"] == ["app"]
    assert "visible" in result["module_to_source"]
    assert "hidden" not in result["module_to_source"]


def test_exclusions_do_not_index_test_or_environment_directories(tmp_path: Path) -> None:
    write(tmp_path, "app/valid.py", "def f(): ...\n")
    for excluded in ("tests", ".venv", "vendor", "build", "__pycache__", ".git", "docs"):
        write(tmp_path, f"{excluded}/broken.py", "not valid Python ???")
    result = inspection(tmp_path, source_root=".", explicitly_selected=True)
    assert result["summary"]["source_files"] == 1
    assert result["summary"]["diagnostic_errors"] == 0


def test_syntax_error_is_diagnosed_with_line_and_not_executed(tmp_path: Path) -> None:
    write(tmp_path, "src/good.py", "class A: pass\n")
    write(tmp_path, "src/bad.py", "def wrong(:\n    pass\n")
    result = inspection(tmp_path)
    assert result["summary"]["source_files"] == 2
    assert result["summary"]["parsed_files"] == 1
    diagnostic = next(d for d in result["diagnostics"] if d["code"] == "syntax_error")
    assert diagnostic["file"] == "src/bad.py"
    assert diagnostic["line"] == 1
    assert diagnostic["severity"] == "error"


def test_source_root_must_exist_and_not_escape_project(tmp_path: Path) -> None:
    for source, code in (("missing", "missing_source_root"), ("../elsewhere", "unsafe_source_root")):
        result = inspection(tmp_path, source_root=source, explicitly_selected=True)
        assert code in {d["code"] for d in result["diagnostics"]}


def test_test_root_cannot_be_project_source_root(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg.py", "class A: pass\n")
    result = inspection(tmp_path, tests_root="src")
    assert "unsafe_tests_root" in {d["code"] for d in result["diagnostics"]}


def test_symlinks_are_rejected_without_opening_sources(tmp_path: Path) -> None:
    write(tmp_path, "src/valid.py", "class A: ...\n")
    outside = write(tmp_path, "elsewhere/other.py", "raise RuntimeError('do not follow')\n")
    link = tmp_path / "src" / "external.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result = inspection(tmp_path)
    assert any(d["code"] == "unsafe_symlink" and d["file"] == "src/external.py" for d in result["diagnostics"])
    assert result["summary"]["source_files"] == 1


def test_mirror_helpers_are_pure_and_accept_windows_separators() -> None:
    mirrors = mirror_paths("src/team/pricing.py", "mytests", testable=True)
    assert mirrors["unit_test"] == "mytests/unit/mirror/src/team/test_pricing.py"
    assert mirrors["interaction_test"] == "mytests/interaction/mirror/src/team/test_pricing_interaction.py"


def test_windows_separator_source_root_path_on_host(tmp_path: Path) -> None:
    write(tmp_path, "src/one.py", "def one(): ...\n")
    result = inspection(tmp_path, source_root=r"src\\", explicitly_selected=True)
    assert result["summary"]["source_files"] == 1


def test_duplicate_overlapping_roots_are_deduplicated(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/item.py", "def go(): ...\n")
    result = inspection(tmp_path, source_root=".", extra_source_roots=("src",), explicitly_selected=True)
    assert result["summary"]["source_files"] == 1
    assert result["files"][0]["module_name"] == "pkg.item"


def test_nonutf8_python_encoding_cookie_is_supported(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "legacy.py").write_bytes(b"# coding: latin-1\nname = 'caf\xe9'\n")
    result = inspection(tmp_path)
    assert result["summary"]["diagnostic_errors"] == 0
    assert result["summary"]["source_files"] == 1


def test_readonly_audit_is_byte_and_tree_stable(tmp_path: Path) -> None:
    write(tmp_path, "src/acme/pricing.py", "def calc(): return 1\n")
    before = sorted((str(p.relative_to(tmp_path)), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file())
    first = inspection(tmp_path)
    second = inspection(tmp_path)
    after = sorted((str(p.relative_to(tmp_path)), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file())
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert before == after


def test_target_lookup_by_path_module_and_symbol(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/service.py", "def process(): ...\n")
    for target in ("src/pkg/service.py", "pkg.service", "pkg.service.process", r"src\\pkg\\service.py"):
        assert inspection(tmp_path, target=target)["target"] == "src/pkg/service.py"
    assert any(d["code"] == "invalid_target" for d in inspection(tmp_path, target="no.such.module")["diagnostics"])


def test_symlinked_source_dir_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "src/valid.py", "def valid(): ...\n")
    directory = tmp_path / "outside"
    write(tmp_path, "outside/evil.py", "raise RuntimeError('must not run')\n")
    try:
        (tmp_path / "src" / "linked").symlink_to(directory, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    result = inspection(tmp_path)
    assert result["summary"]["source_files"] == 1
    assert any(d["code"] == "unsafe_symlink" for d in result["diagnostics"])


def test_symlinked_source_root_is_rejected(tmp_path: Path) -> None:
    source = write(tmp_path, "source/m.py", "def m(): ...\n").parent
    try:
        (tmp_path / "src").symlink_to(source, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    result = inspection(tmp_path, source_root="src", explicitly_selected=True)
    assert any(d["code"] == "unsafe_symlink" for d in result["diagnostics"])


def test_test_root_outside_project_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "src/m.py", "def m(): ...\n")
    result = inspection(tmp_path, tests_root="../other_tests")
    assert "unsafe_tests_root" in {d["code"] for d in result["diagnostics"]}


def test_source_root_subfolder_of_tests_root_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "src/m.py", "def m(): ...\n")
    result = inspection(tmp_path, tests_root=".")
    assert "unsafe_tests_root" in {d["code"] for d in result["diagnostics"]}


def test_invalid_relative_import_is_structural_error(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/mod.py", "from ...outside import Stuff\n")
    result = inspection(tmp_path)
    assert any(d["code"] == "invalid_relative_import" for d in result["diagnostics"])


def test_unresolved_inner_package_import_warns(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/__init__.py", "")
    write(tmp_path, "src/pkg/use.py", "import pkg.nonexistent\n")
    result = inspection(tmp_path)
    assert any(d["code"] == "unresolved_internal_import" for d in result["diagnostics"])


def test_namespace_package_is_supported_without_init(tmp_path: Path) -> None:
    write(tmp_path, "src/pkg/nested/impl.py", "class Service: ...\n")
    write(tmp_path, "src/pkg/nested/use.py", "from .impl import Service\n")
    result = inspection(tmp_path)
    assert result["summary"]["diagnostic_errors"] == 0
    assert result["module_to_source"]["pkg.nested.impl"] == "src/pkg/nested/impl.py"
    use = next(f for f in result["files"] if f["module_name"] == "pkg.nested.use")
    assert use["imports"][0]["resolved_symbol"] == "pkg.nested.impl.Service"


def test_case_collisions_report_portability_errors(tmp_path: Path) -> None:
    write(tmp_path, "src/Foo.py", "class A: pass\n")
    write(tmp_path, "src/foo.py", "class B: pass\n")
    # Windows disallows distinct case-only file names; skip on that filesystem.
    if len({p.name for p in (tmp_path / "src").iterdir()}) < 2:
        pytest.skip("case insensitive filesystem")
    result = inspection(tmp_path)
    assert "case_collision" in {d["code"] for d in result["diagnostics"]}


def test_aliases_of_dynamic_imports_are_diagnosed(tmp_path: Path) -> None:
    write(tmp_path, "src/work.py", '''
import importlib as il
from importlib import import_module as load

def launch(name):
    return il.import_module(name), load(name), __import__(name)
''')
    result = inspection(tmp_path)
    names = [x["name"] for x in result["files"][0]["dynamic_imports"]]
    assert names == ["il.import_module", "load", "__import__"]
    assert len([x for x in result["diagnostics"] if x["code"] == "dynamic_import"]) == 3


def test_conflicted_module_symbols_cannot_be_targeted(tmp_path: Path) -> None:
    write(tmp_path, "src/x.py", "class FromFile: pass\n")
    write(tmp_path, "src/x/__init__.py", "class FromPackage: pass\n")
    result = inspection(tmp_path, target="x.FromFile")
    assert result["target"] is None
    assert "x.FromFile" not in result["symbol_to_source"]
    assert any(d["code"] == "invalid_target" for d in result["diagnostics"])
