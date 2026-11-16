"""State Tree —— 公理一：状态即真相 (Single Source of Truth)。

整个应用的全部可变状态收敛为一棵结构化、带路径的全局状态树。
根下分两个子树：
  - project: 领域状态（层级/运动副/驱动/测距……对应 ProjectSpec）
  - ui:      界面状态（布局、折叠、主题、变更高亮……）UI 也是状态。

任何"当前值"都是这棵树上一个可寻址节点。寻址采用稳定路径：
  - dict 用键名：           project.metadata.name
  - list 用实体ID（若有）： project.layers.@layer_x.joints.@joint_y.axis
  - list 无ID时退化为序号： ui.panels.0.collapsed
稳定路径保证插入/删除兄弟节点后，LLM 先前保存的目标路径不漂移。
"""
from __future__ import annotations

import copy
import json
from typing import Any


class PathError(KeyError):
    pass


class StateTree:
    def __init__(self, root: dict[str, Any] | None = None) -> None:
        self._root: dict[str, Any] = root if root is not None else {"project": {}, "ui": {}}

    # ---- 序列化：序列化即"保存项目"，反序列化即"加载项目"（含 UI 布局） ----
    def to_json(self) -> str:
        return json.dumps(self._root, ensure_ascii=False, indent=2)

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self._root)

    def replace(self, root: dict[str, Any]) -> None:
        self._root = copy.deepcopy(root)

    def adopt(self, root: dict[str, Any]) -> None:
        """Take ownership of a private root without another full-tree copy."""
        if not isinstance(root, dict):
            raise TypeError("state root must be an object")
        self._root = root

    def delete(self, path: str) -> Any:
        """Delete an existing node and return its previous value."""
        node, key = self._locate(path, create=False)
        before = copy.deepcopy(self._read(node, key))
        if isinstance(node, list):
            del node[self._list_index(node, key)]
        elif isinstance(node, dict):
            del node[key]
        else:
            raise PathError(f"cannot delete {key} from scalar")
        return before

    @classmethod
    def from_dict(cls, root: dict[str, Any]) -> "StateTree":
        return cls(copy.deepcopy(root))

    @property
    def root(self) -> dict[str, Any]:
        return self._root

    # ---- 路径寻址 ----
    def get(self, path: str) -> Any:
        """Return a private copy so callers cannot mutate authoritative state."""
        node, key = self._locate(path, create=False)
        return copy.deepcopy(self._read(node, key))

    def peek(self, path: str) -> Any:
        """Zero-copy internal read for code paths proven not to mutate values."""
        node, key = self._locate(path, create=False)
        return self._read(node, key)

    def has(self, path: str) -> bool:
        try:
            self.peek(path)
            return True
        except (PathError, KeyError, IndexError):
            return False

    def set(self, path: str, value: Any) -> Any:
        """写入并返回该路径的旧值（供事件 inverse 使用）。"""
        node, key = self._locate(path, create=True)
        before = self._read_safe(node, key)
        self._write(node, key, copy.deepcopy(value))
        return before

    def set_existing(self, path: str, value: Any) -> Any:
        """Set an existing node; unlike ``set`` this never invents schema keys."""
        node, key = self._locate(path, create=False)
        before = copy.deepcopy(self._read(node, key))
        self._write(node, key, copy.deepcopy(value))
        return before

    def set_owned(self, path: str, value: Any) -> Any:
        """Install an already-private value and transfer ownership to this tree.

        Internal transaction hot paths use this only on a private shadow tree.
        The removed value is also private, so returning it without another
        deepcopy cannot expose authoritative state.
        """
        node, key = self._locate(path, create=True)
        try:
            before = self._read(node, key)
        except (PathError, KeyError, IndexError):
            before = None
        self._write(node, key, value)
        return before

    # ---- 内部：解析路径 ----
    @staticmethod
    def _tokens(path: str) -> list[str]:
        if not path:
            raise PathError("empty path")
        return path.split(".")

    def _locate(self, path: str, create: bool) -> tuple[Any, str]:
        tokens = self._tokens(path)
        current: Any = self._root
        for token in tokens[:-1]:
            current = self._descend(current, token, create)
        return current, tokens[-1]

    def _descend(self, node: Any, token: str, create: bool) -> Any:
        if isinstance(node, list):
            return node[self._list_index(node, token)]
        if isinstance(node, dict):
            if token not in node:
                if not create:
                    raise PathError(f"missing key: {token}")
                node[token] = {}
            return node[token]
        raise PathError(f"cannot descend into scalar via: {token}")

    @staticmethod
    def _list_index(items: list[Any], token: str) -> int:
        if token.startswith("@"):
            entity_id = token[1:]
            for i, item in enumerate(items):
                if isinstance(item, dict) and item.get("id") == entity_id:
                    return i
            raise PathError(f"entity not found: {entity_id}")
        return int(token)

    def _read(self, node: Any, key: str) -> Any:
        if isinstance(node, list):
            return node[self._list_index(node, key)]
        if isinstance(node, dict):
            if key not in node:
                raise PathError(f"missing key: {key}")
            return node[key]
        raise PathError(f"cannot read {key} from scalar")

    def _read_safe(self, node: Any, key: str) -> Any:
        try:
            return copy.deepcopy(self._read(node, key))
        except (PathError, KeyError, IndexError):
            return None

    def _write(self, node: Any, key: str, value: Any) -> None:
        if isinstance(node, list):
            node[self._list_index(node, key)] = value
        elif isinstance(node, dict):
            node[key] = value
        else:
            raise PathError(f"cannot write {key} into scalar")
