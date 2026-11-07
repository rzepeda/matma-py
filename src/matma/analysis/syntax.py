"""Syntax-only module inventory. Never import or execute a consumer module."""

from __future__ import annotations

import ast
from collections.abc import Iterable


def _full_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _full_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


class SyntaxVisitor(ast.NodeVisitor):
    """Collect declarations, raw imports and static references, with scope data."""

    def __init__(self, tree: ast.Module) -> None:
        self.symbols: list[dict] = []
        self.imports: list[dict] = []
        self.dynamic_imports: list[dict] = []
        self.references: list[dict] = []
        self.scope: list[tuple[str, str]] = []
        self.type_only = False
        self.ref_kind = "usage"
        self.typing_aliases = {"typing"}
        self.checking_aliases = {"TYPE_CHECKING"}
        self.importlib_aliases = {"importlib"}
        self.import_module_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.typing_aliases.update(a.asname or "typing" for a in node.names if a.name == "typing")
                self.importlib_aliases.update(a.asname or "importlib" for a in node.names if a.name == "importlib")
            elif isinstance(node, ast.ImportFrom) and node.module == "typing":
                self.checking_aliases.update(a.asname or "TYPE_CHECKING" for a in node.names if a.name == "TYPE_CHECKING")
            elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
                self.import_module_aliases.update(a.asname or "import_module" for a in node.names if a.name == "import_module")
        self.explicit_exports = self._static_all(tree.body)
        self.visit(tree)

    @staticmethod
    def _static_all(body: Iterable[ast.stmt]) -> list[str] | None:
        for node in body:
            value = None
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__":
                value = node.value
            if isinstance(value, (ast.List, ast.Tuple)) and all(
                isinstance(item, ast.Constant) and isinstance(item.value, str) for item in value.elts
            ):
                return [item.value for item in value.elts]  # type: ignore[union-attr]
        return None

    def _scope(self) -> str:
        return ".".join(item[0] for item in self.scope)

    def _symbol(self, node: ast.AST, name: str, kind: str) -> None:
        parent = self._scope()
        self.symbols.append({
            "name": name,
            "qualname": f"{parent}.{name}" if parent else name,
            "kind": kind,
            "line": node.lineno,
            "column": node.col_offset,
            "scope": parent or None,
        })

    def _tag(self, kind: str, *nodes: ast.AST | None) -> None:
        previous = self.ref_kind
        self.ref_kind = kind
        try:
            for node in nodes:
                if node is not None:
                    self.visit(node)
        finally:
            self.ref_kind = previous

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._symbol(node, node.name, "nested_class" if self.scope else "class")
        for base in node.bases:
            self._tag("inheritance", base)
        for keyword in node.keywords:
            self._tag("inheritance", keyword.value)
        for deco in node.decorator_list:
            self._tag("decorator", deco)
        for param in node.type_params if hasattr(node, "type_params") else ():
            self._tag("annotation", param)
        self.scope.append((node.name, "class"))
        try:
            for stmt in node.body:
                self.visit(stmt)
        finally:
            self.scope.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, asynchronous: bool) -> None:
        parent = self.scope[-1][1] if self.scope else None
        kind = ("async_method" if asynchronous else "method") if parent == "class" else (
            "nested_async_function" if asynchronous else "nested_function"
        ) if parent else ("async_function" if asynchronous else "function")
        self._symbol(node, node.name, kind)
        for deco in node.decorator_list:
            self._tag("decorator", deco)
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            self._tag("usage", default)
        parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            parameters.append(node.args.vararg)
        if node.args.kwarg:
            parameters.append(node.args.kwarg)
        for param in parameters:
            self._tag("annotation", param.annotation)
        self._tag("annotation", node.returns)
        for param in node.type_params if hasattr(node, "type_params") else ():
            self._tag("annotation", param)
        self.scope.append((node.name, "function"))
        try:
            for stmt in node.body:
                self.visit(stmt)
        finally:
            self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, True)

    def _import(self, *, node: ast.AST, form: str, module: str | None, alias: ast.alias, level: int) -> None:
        bound = alias.asname or (alias.name.partition(".")[0] if form == "import" else alias.name)
        self.imports.append({
            "form": form,
            "module": module,
            "name": alias.name,
            "asname": alias.asname,
            "bound_name": bound,
            "level": level,
            "line": node.lineno,
            "column": node.col_offset,
            "scope": self._scope() or None,
            "type_only": self.type_only,
        })

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._import(node=node, form="import", module=alias.name, alias=alias, level=0)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._import(node=node, form="from", module=node.module, alias=alias, level=node.level)

    def _type_test(self, node: ast.AST) -> bool:
        name = _full_name(node)
        return name in self.checking_aliases or any(name == f"{alias}.TYPE_CHECKING" for alias in self.typing_aliases)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        condition = node.test
        negative = isinstance(condition, ast.UnaryOp) and isinstance(condition.op, ast.Not)
        recognized = self._type_test(condition.operand if negative else condition)
        previous = self.type_only
        try:
            self.type_only = previous or (recognized and not negative)
            for stmt in node.body:
                self.visit(stmt)
            self.type_only = previous or (recognized and negative)
            for stmt in node.orelse:
                self.visit(stmt)
        finally:
            self.type_only = previous

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        self._tag("annotation", node.annotation)
        if node.value:
            self.visit(node.value)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load):
            full = _full_name(node)
            if full:
                self.references.append({
                    "name": full, "kind": self.ref_kind, "line": node.lineno,
                    "column": node.col_offset, "scope": self._scope() or None,
                    "type_only": self.type_only,
                })
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        full = _full_name(node.func)
        # Report common runtime import mechanisms, without executing them or
        # fabricating graph edges. Aliases may hide further dynamic imports.
        if full == "__import__" or full in self.import_module_aliases or any(
            full == f"{alias}.import_module" for alias in self.importlib_aliases
        ):
            self.dynamic_imports.append({
                "name": full, "line": node.lineno, "column": node.col_offset,
                "scope": self._scope() or None, "type_only": self.type_only,
            })
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.references.append({
                "name": node.id, "kind": self.ref_kind, "line": node.lineno,
                "column": node.col_offset, "scope": self._scope() or None,
                "type_only": self.type_only,
            })
