from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MANAGERS = {"module", "cgscc", "function", "loop", "loop-mssa"}


def split_pipeline(pipeline: str) -> list[str]:
    items: list[str] = []
    start = 0
    angle = paren = 0
    for index, char in enumerate(pipeline):
        if char == "<":
            angle += 1
        elif char == ">":
            angle = max(0, angle - 1)
        elif char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "," and angle == 0 and paren == 0:
            item = pipeline[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
    tail = pipeline[start:].strip()
    if tail:
        items.append(tail)
    return items


def join_pipeline(items: list[str]) -> str:
    return ",".join(item for item in items if item)


def pass_name(token: str) -> str:
    token = token.strip()
    if "(" in token and token.endswith(")"):
        return token.split("(", 1)[0].split("<", 1)[0]
    if "<" in token:
        return token.split("<", 1)[0]
    return token


def _split_name_parameters(token: str) -> tuple[str, str | None]:
    token = token.strip()
    if "<" not in token or not token.endswith(">"):
        return token, None
    index = token.index("<")
    return token[:index], token[index + 1 : -1]


def normalize_opt_option(name: str, value: str | None, catalog: dict[str, Any] | None = None) -> str:
    clean = name.strip().lstrip("-")
    if not clean:
        raise ValueError("empty opt option name")
    cli_name = f"-{clean}"
    option = (catalog or {}).get("opt_options", {}).get(clean)
    if option:
        cli_name = option.get("cli_name", cli_name)
    if value is None or value == "":
        return cli_name
    lower = str(value).lower()
    if lower in {"false", "0", "no"}:
        return f"{cli_name}=false"
    if lower in {"true", "1", "yes"}:
        return f"{cli_name}=true"
    return f"{cli_name}={value}"


@dataclass
class PipelineNode:
    kind: str
    name: str | None = None
    manager: str | None = None
    parameters: str | None = None
    children: list["PipelineNode"] = field(default_factory=list)
    origin: str = "parent"

    def clone(self) -> "PipelineNode":
        return PipelineNode(
            kind=self.kind,
            name=self.name,
            manager=self.manager,
            parameters=self.parameters,
            children=[child.clone() for child in self.children],
            origin=self.origin,
        )

    def label(self) -> str:
        if self.kind == "manager":
            return self.manager or ""
        return self.name or ""

    def serialize(self) -> str:
        if self.kind == "root":
            return join_pipeline([child.serialize() for child in self.children])
        if self.kind == "manager":
            head = self.manager or ""
            if self.parameters:
                head += f"<{self.parameters}>"
            return f"{head}({join_pipeline([child.serialize() for child in self.children])})"
        head = self.name or ""
        if self.parameters:
            head += f"<{self.parameters}>"
        return head

    def to_dict(self, max_depth: int = 4) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.kind == "manager":
            data["manager"] = self.manager
        if self.kind == "pass":
            data["name"] = self.name
        if self.parameters:
            data["parameters"] = self.parameters
        if self.children and max_depth > 0:
            data["children"] = [child.to_dict(max_depth=max_depth - 1) for child in self.children]
        return data


@dataclass
class NodeRef:
    parent: PipelineNode
    index: int
    node: PipelineNode
    occurrence_label: str
    parent_manager: str


@dataclass
class PipelineEditResult:
    pipeline: str
    opt_options: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    invalid_errors: list[str] = field(default_factory=list)
    ast: dict[str, Any] | None = None

    @property
    def valid(self) -> bool:
        return not self.invalid_errors


def _manager_head(token: str) -> tuple[str, str | None] | None:
    if not token.endswith(")") or "(" not in token:
        return None
    open_index = None
    angle = 0
    for index, char in enumerate(token):
        if char == "<":
            angle += 1
        elif char == ">":
            angle = max(0, angle - 1)
        elif char == "(" and angle == 0:
            open_index = index
            break
    if open_index is None:
        return None
    head = token[:open_index]
    manager, params = _split_name_parameters(head)
    if manager not in MANAGERS:
        return None
    return manager, params


def parse_pipeline(pipeline: str) -> PipelineNode:
    return PipelineNode(kind="root", children=[parse_pipeline_node(item) for item in split_pipeline(pipeline)])


def parse_pipeline_node(token: str) -> PipelineNode:
    token = token.strip()
    manager = _manager_head(token)
    if manager:
        manager_name, params = manager
        open_index = token.find("(")
        inner = token[open_index + 1 : -1]
        return PipelineNode(
            kind="manager",
            manager=manager_name,
            parameters=params,
            children=[parse_pipeline_node(item) for item in split_pipeline(inner)],
            origin="parent",
        )
    name, params = _split_name_parameters(token)
    return PipelineNode(kind="pass", name=name, parameters=params, origin="parent")


def node_from_fragment(spec: dict[str, Any]) -> PipelineNode:
    kind = spec.get("kind")
    origin = str(spec.get("origin", "planner_new"))
    if kind == "manager":
        manager = spec.get("manager")
        return PipelineNode(
            kind="manager",
            manager=str(manager),
            parameters=spec.get("parameters"),
            children=[node_from_fragment(child) for child in spec.get("passes", spec.get("children", []))],
            origin=origin,
        )
    if kind == "pass":
        return PipelineNode(kind="pass", name=str(spec.get("name")), parameters=spec.get("parameters"), origin=origin)
    raise ValueError(f"unknown fragment node kind: {kind}")


def _parse_anchor(anchor: str) -> tuple[str, int]:
    if "#" not in anchor:
        return anchor, 1
    name, occurrence = anchor.rsplit("#", 1)
    return name, int(occurrence)


def enumerate_nodes(root: PipelineNode) -> list[NodeRef]:
    counts: dict[str, int] = {}
    refs: list[NodeRef] = []

    def visit(parent: PipelineNode, parent_manager: str) -> None:
        for index, child in enumerate(parent.children):
            label = child.label()
            counts[label] = counts.get(label, 0) + 1
            refs.append(NodeRef(parent, index, child, f"{label}#{counts[label]}", parent_manager))
            if child.kind == "manager":
                visit(child, child.manager or parent_manager)

    visit(root, "module")
    return refs


def find_node(root: PipelineNode, anchor: str, *, parent_manager: str | None = None) -> NodeRef | None:
    name, occurrence = _parse_anchor(anchor)
    for ref in enumerate_nodes(root):
        if ref.node.label() == name and ref.occurrence_label.endswith(f"#{occurrence}"):
            if parent_manager is None or ref.parent_manager == parent_manager:
                return ref
    return None


def find_manager(root: PipelineNode, manager_type: str, occurrence: int = 1) -> PipelineNode | None:
    seen = 0
    if manager_type == "module":
        return root
    for ref in enumerate_nodes(root):
        if ref.node.kind == "manager" and ref.node.manager == manager_type:
            seen += 1
            if seen == occurrence:
                return ref.node
    return None


def local_region(
    pipeline: str,
    *,
    parent_manager: str = "function",
    start_anchor: str = "loop-distribute#1",
    end_anchor: str = "loop-vectorize#1",
) -> dict[str, Any]:
    root = parse_pipeline(pipeline)
    parent = find_manager(root, parent_manager)
    if parent is None:
        return {"parent_manager": parent_manager, "nodes": []}
    start = find_node(parent, start_anchor)
    end = find_node(parent, end_anchor)
    if start is None or end is None:
        return {"parent_manager": parent_manager, "nodes": [child.to_dict(max_depth=3) for child in parent.children]}
    lo, hi = sorted([start.index, end.index])
    return {
        "parent_manager": parent_manager,
        "start_anchor": start_anchor,
        "end_anchor": end_anchor,
        "nodes": [child.to_dict(max_depth=3) for child in parent.children[lo : hi + 1]],
    }


def pipeline_outline(pipeline: str, limit: int = 120) -> list[str]:
    refs = enumerate_nodes(parse_pipeline(pipeline))
    return [ref.occurrence_label for ref in refs[:limit]]


def _pass_catalog_entry(catalog: dict[str, Any], name: str) -> dict[str, Any] | None:
    return catalog.get("passes", {}).get(name)


def _validate_node(node: PipelineNode, parent_manager: str, catalog: dict[str, Any], errors: list[str]) -> None:
    if node.kind == "manager":
        if node.manager not in catalog.get("managers", {}):
            errors.append(f"unknown manager: {node.manager}")
        for child in node.children:
            _validate_node(child, node.manager or parent_manager, catalog, errors)
        return
    name = node.name or ""
    entry = _pass_catalog_entry(catalog, name)
    if entry is None:
        if node.origin in {"baseline", "parent"}:
            return
        errors.append(f"unknown pass: {name}")
        return
    allowed = entry.get("allowed_managers", [])
    required = entry.get("required_manager")
    if required and parent_manager != required:
        errors.append(f"pass {name} requires manager {required}, got {parent_manager}")
    elif allowed and parent_manager not in allowed:
        errors.append(f"pass {name} is not allowed in manager {parent_manager}; allowed={allowed}")
    schema = entry.get("parameter_schema", [])
    if node.parameters and schema:
        allowed_keys = {str(item).split("=", 1)[0].removeprefix("no-") for item in schema}
        for param in [item for item in node.parameters.split(";") if item]:
            key = param.split("=", 1)[0].removeprefix("no-")
            if key not in allowed_keys:
                errors.append(f"pass {name} has unknown parameter {param}")


def validate_fragment(nodes: list[PipelineNode], parent_manager: str, catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for node in nodes:
        _validate_node(node, parent_manager, catalog, errors)
    return errors


def mark_inherited_nodes(replacement: list[PipelineNode], original: list[PipelineNode]) -> None:
    for index, node in enumerate(replacement):
        if index < len(original) and node.serialize() == original[index].serialize():
            node.origin = "parent"
        elif node.origin in {"baseline", "parent"}:
            node.origin = "planner_modified"


class PipelineEditor:
    def __init__(self, base_pipeline: str, *, catalog: dict[str, Any] | None = None, valid_opt_options: set[str] | None = None) -> None:
        self.root = parse_pipeline(base_pipeline.strip())
        self.catalog = catalog or {}
        self.valid_opt_options = valid_opt_options
        self.opt_options: dict[str, str | None] = {}
        self.warnings: list[str] = []
        self.invalid_errors: list[str] = []

    def apply_candidate(self, candidate: dict[str, Any]) -> PipelineEditResult:
        for edit in candidate.get("edits", []):
            self.apply_edit(edit)
        for option in candidate.get("opt_options", []):
            self.set_opt_option(option)
        # Compatibility for older mock/artifacts.
        for operation in candidate.get("operations", []):
            self.apply_legacy_operation(operation)
        return self.result()

    def apply_all(self, operations: list[dict[str, Any]]) -> PipelineEditResult:
        for operation in operations:
            self.apply_legacy_operation(operation)
        return self.result()

    def result(self) -> PipelineEditResult:
        options: list[str] = []
        for name, value in sorted(self.opt_options.items()):
            try:
                options.append(normalize_opt_option(name, value, self.catalog))
            except ValueError as exc:
                self.invalid_errors.append(str(exc))
        return PipelineEditResult(
            self.root.serialize(),
            options,
            self.warnings,
            self.invalid_errors,
            self.root.to_dict(max_depth=8),
        )

    def set_opt_option(self, option: dict[str, Any]) -> None:
        name = str(option.get("name", "")).lstrip("-")
        known = set(self.catalog.get("opt_options", {}).keys())
        if self.valid_opt_options is not None:
            known |= {item.lstrip("-") for item in self.valid_opt_options}
        if known and name not in known:
            self.invalid_errors.append(f"unknown opt option: {name}")
            return
        self.opt_options[name] = None if "value" not in option else str(option.get("value"))

    def _target_parent(self, target: dict[str, Any]) -> PipelineNode | None:
        manager = str(target.get("parent_manager", "module"))
        occurrence = int(target.get("parent_occurrence", 1))
        parent = find_manager(self.root, manager, occurrence)
        if parent is None:
            self.invalid_errors.append(f"parent manager not found: {manager}#{occurrence}")
        return parent

    def _fragment(self, edit: dict[str, Any], parent_manager: str) -> list[PipelineNode]:
        specs = edit.get("replacement", edit.get("fragment", []))
        nodes = [node_from_fragment(spec) for spec in specs]
        if self.catalog:
            self.invalid_errors.extend(validate_fragment(nodes, parent_manager, self.catalog))
        return nodes

    def _validate_fragment(self, nodes: list[PipelineNode], parent_manager: str) -> None:
        if self.catalog:
            self.invalid_errors.extend(validate_fragment(nodes, parent_manager, self.catalog))

    def apply_edit(self, edit: dict[str, Any]) -> None:
        kind = edit.get("type")
        if kind == "replace_region":
            self.replace_region(edit)
        elif kind == "insert_fragment":
            self.insert_fragment(edit)
        elif kind == "remove_node":
            self.remove_node(edit)
        elif kind == "move_node":
            self.move_node(edit)
        elif kind == "set_pass_parameter":
            self.set_pass_parameter(edit)
        else:
            self.invalid_errors.append(f"unknown edit type: {kind}")

    def replace_region(self, edit: dict[str, Any]) -> None:
        target = edit.get("target", {})
        parent = self._target_parent(target)
        if parent is None:
            return
        parent_manager = parent.manager or "module"
        start = find_node(parent, str(target.get("start_anchor", "")))
        end = find_node(parent, str(target.get("end_anchor", "")))
        if start is None or end is None:
            self.invalid_errors.append(f"replace_region anchors not found: {target}")
            return
        lo, hi = sorted([start.index, end.index])
        replacement = [node_from_fragment(spec) for spec in edit.get("replacement", edit.get("fragment", []))]
        mark_inherited_nodes(replacement, parent.children[lo : hi + 1])
        self._validate_fragment(replacement, parent_manager)
        parent.children[lo : hi + 1] = replacement

    def insert_fragment(self, edit: dict[str, Any]) -> None:
        target = edit.get("target", {})
        parent = self._target_parent(target)
        if parent is None:
            return
        parent_manager = parent.manager or "module"
        fragment = self._fragment(edit, parent_manager)
        anchor = target.get("anchor")
        if not anchor:
            parent.children.extend(fragment)
            return
        ref = find_node(parent, str(anchor))
        if ref is None:
            self.invalid_errors.append(f"insert_fragment anchor not found: {anchor}")
            return
        position = target.get("position", "after")
        index = ref.index if position == "before" else ref.index + 1
        parent.children[index:index] = fragment

    def remove_node(self, edit: dict[str, Any]) -> None:
        target = edit.get("target", {})
        ref = find_node(self.root, str(target.get("anchor", "")), parent_manager=target.get("parent_manager"))
        if ref is None:
            self.invalid_errors.append(f"remove_node anchor not found: {target}")
            return
        ref.parent.children.pop(ref.index)

    def move_node(self, edit: dict[str, Any]) -> None:
        target = edit.get("target", {})
        src = find_node(self.root, str(target.get("source_anchor", "")), parent_manager=target.get("source_parent_manager"))
        dst = find_node(self.root, str(target.get("dest_anchor", "")), parent_manager=target.get("dest_parent_manager"))
        if src is None or dst is None:
            self.invalid_errors.append(f"move_node anchor not found: {target}")
            return
        node = src.parent.children.pop(src.index)
        dst = find_node(self.root, str(target.get("dest_anchor", "")), parent_manager=target.get("dest_parent_manager"))
        if dst is None:
            self.invalid_errors.append(f"move_node destination disappeared: {target}")
            return
        index = dst.index if target.get("position", "after") == "before" else dst.index + 1
        dst.parent.children.insert(index, node)

    def set_pass_parameter(self, edit: dict[str, Any]) -> None:
        target = edit.get("target", {})
        ref = find_node(self.root, str(target.get("anchor", edit.get("pass", ""))), parent_manager=target.get("parent_manager"))
        if ref is None or ref.node.kind != "pass":
            self.invalid_errors.append(f"set_pass_parameter target not found: {target or edit}")
            return
        key = str(edit.get("name"))
        value = str(edit.get("value"))
        params = ref.node.parameters.split(";") if ref.node.parameters else []
        replaced = False
        new_params: list[str] = []
        for param in params:
            if param.split("=", 1)[0] == key:
                new_params.append(f"{key}={value}")
                replaced = True
            else:
                new_params.append(param)
        if not replaced:
            new_params.append(f"{key}={value}")
        ref.node.parameters = ";".join(new_params)

    def apply_legacy_operation(self, operation: dict[str, Any]) -> None:
        kind = operation.get("type")
        if kind in {"set_opt_option", "set_option"}:
            self.set_opt_option(operation)
            return
        if kind == "unset_opt_option":
            self.opt_options.pop(str(operation.get("name", "")).lstrip("-"), None)
            return
        if kind == "set_pass_parameter":
            self.set_pass_parameter({"target": {"anchor": operation.get("pass")}, "name": operation.get("name"), "value": operation.get("value")})
            return
        if kind == "insert_pass":
            self.insert_fragment(
                {
                    "type": "insert_fragment",
                    "target": {"parent_manager": operation.get("parent_manager", "function"), "anchor": operation.get("anchor"), "position": operation.get("position", "after")},
                    "fragment": [{"kind": "pass", "name": operation.get("pass")}],
                }
            )
            return
        self.invalid_errors.append(f"legacy operation requires nested edit schema: {kind}")
