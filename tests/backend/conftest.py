# -*- coding: utf-8 -*-
"""pytest 公共夹具：导入 server 引擎，强制离线（禁止真实 AI 调用），提供干净初始状态。

运行方式（项目根目录）：
    python -m pytest tests/backend -q
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # 项目根
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DEEPSEEK_API_KEY", "")  # 测试环境禁止真实 key

import server  # noqa: E402

# —— 安全闸门：整个测试过程不得触碰真实 AI ——
server.API_KEY = ""
server._OPENAI_OK = False


@pytest.fixture(autouse=True)
def _no_random_side_effect(monkeypatch):
    """每个用例前固定随机种子，保证结果可复现。"""
    random.seed(20260912)


@pytest.fixture(scope="session")
def engine():
    return server


@pytest.fixture
def base_state(engine):
    """标准初始状态（炼气一层、满血、无灵根）。每次返回全新对象，互不污染。"""
    return engine.sanitize_state({
        "realm_index": 0, "hp": 100, "hp_max": 100, "qi": 50, "qi_max": 50,
        "exp": 0, "spirit_stones": 100, "spirit_root": "",
        "items": [{"name": "回气丹", "qty": 2, "rarity": "下品"}],
        "memory": [], "recent": [], "npcs": [], "style_echo": [],
        "memory_summary": "", "reincarnations": [],
        "pending_events": [], "fail_streak": 0,
        "last_near_death_turn": -999, "turn": 0,
    })


@pytest.fixture
def full_state(engine, base_state):
    """修为圆满、物资充裕的状态，用于触发冲关/濒死等边界。"""
    s = dict(base_state)
    s["exp"] = engine.exp_max_of(0)
    s["spirit_stones"] = 500
    s["items"] = [
        {"name": "回气丹", "qty": 1, "rarity": "下品"},
        {"name": "疗伤丹", "qty": 1, "rarity": "中品"},
        {"name": "凝气丹", "qty": 1, "rarity": "上品"},
        {"name": "清心丹", "qty": 1, "rarity": "下品"},
        {"name": "辟谷丹", "qty": 1, "rarity": "下品"},
        {"name": "碎星石", "qty": 1, "rarity": "下品"},
    ]
    return s


class FakeReq:
    """duck-typed ActReq：/api/act 只用到 action 与 last_choices 两个属性。"""

    def __init__(self, state=None, action=None, last_choices=None):
        self.state = state or {}
        self.action = action or {}
        self.last_choices = last_choices if last_choices is not None else []


@pytest.fixture(scope="session")
def client(engine):
    """FastAPI 测试客户端（进程内调用，不起端口）。"""
    from fastapi.testclient import TestClient

    return TestClient(engine.app)


@pytest.fixture
def fake_req():
    return FakeReq
