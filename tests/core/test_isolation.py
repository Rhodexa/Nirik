"""Architecture guards: core stays bpy-free, nirik never touches dev tooling."""

import ast
from pathlib import Path

import pytest

NIRIK = Path(__file__).resolve().parents[2] / "nirik"
BLENDER_MODULES = {"bpy", "mathutils", "bmesh", "gpu", "gpu_extras", "blf", "bpy_extras", "addon_utils"}
DEV_MODULES = {"devtools", "fla_inspect", "fla_ole2", "parse_ole2", "ir", "compose", "export_svg"}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", sorted((NIRIK / "core").rglob("*.py")), ids=lambda p: p.name)
def test_core_never_imports_blender(path):
    assert not imported_roots(path) & BLENDER_MODULES


@pytest.mark.parametrize("path", sorted(NIRIK.rglob("*.py")), ids=lambda p: str(p.relative_to(NIRIK)))
def test_nirik_never_imports_dev_tooling(path):
    assert not imported_roots(path) & DEV_MODULES
