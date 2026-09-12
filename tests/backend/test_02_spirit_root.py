# -*- coding: utf-8 -*-
"""灵根系统：抽取合法性、格式校验、五行克制、修为系数。

灵根决定玩家整局的成长上限，是唯一的「天赋」变量，
校验失效会让玩家自主伪造天灵根，所以 is_valid_spirit_root 重点做对抗性测试。
"""
import random

import pytest


class TestSpiritRootRolling:
    def test_roll_always_produces_valid_name(self, engine):
        """大量抽样：无论随机如何，产出必须全部通过校验且不越权。"""
        roots = {engine.roll_spirit_root() for _ in range(3000)}
        for r in roots:
            assert engine.is_valid_spirit_root(r), f"掷出非法灵根: {r}"

    def test_distribution_follows_weights(self, engine):
        """伪灵根（最差）权重 0.40，天灵根（最好）0.01 —— 检查 rarity 梯度。"""
        counts = {"天灵根": 0, "单灵根": 0, "双灵根": 0, "三灵根": 0, "四灵根": 0}
        n = 20000
        for _ in range(n):
            # 注意：每次外层循环只能掷一次，否则条件重采样会扭曲分布
            root = engine.roll_spirit_root()
            hit = next((p for p in counts if root.startswith(p)), None)
            if hit:
                counts[hit] += 1
        assert sum(counts.values()) == n, "存在未被归类到任何档位的灵根"
        for a, b in [("天灵根", "单灵根"), ("单灵根", "双灵根"),
                     ("双灵根", "三灵根"), ("三灵根", "四灵根")]:
            assert counts[a] < counts[b], f"{a} 出现频率应低于 {b}"
        # 与权重表逐项比对（允许 1.5% 采样波动）
        for prefix, expect in [("天灵根", 0.01), ("单灵根", 0.09), ("双灵根", 0.20),
                               ("三灵根", 0.30), ("四灵根", 0.40)]:
            assert counts[prefix] / n == pytest.approx(expect, abs=0.015), \
                f"{prefix} 实测占比 {counts[prefix]/n:.3f} 偏离权重 {expect}"

    def test_roll_is_random(self, engine):
        random.seed(7)
        a = [engine.roll_spirit_root() for _ in range(20)]
        random.seed(8)
        b = [engine.roll_spirit_root() for _ in range(20)]
        assert a != b, "灵根抽取未接入随机数（种子变了结果不变）"


class TestSpiritRootValidation:
    @pytest.mark.parametrize("name,expected", [
        ("天灵根·火", True),
        ("单灵根·水", True),
        ("双灵根·金木", True),
        ("三灵根·金木水", True),
        ("四灵根·伪灵根", True),  # 唯一合法的四灵根
        ("三灵根·火", False),      # 前缀与元素数量不符
        ("双灵根·金木水", False),
        ("天灵根·金木", False),
        ("五灵根·金木水火土", False),  # 不存在的档位
        ("火", False),                 # 无分隔符
        ("", False),
        (None, False),
        ("四灵根·金木水火", False),  # 四灵根必须是伪灵根
        ("三灵根·金金水", False),      # 重复元素
        ("三灵根·金木X", False),       # 非五行字符
        ("天灵根·", False),            # 空元素
    ])
    def test_validation_matrix(self, engine, name, expected):
        assert engine.is_valid_spirit_root(name) is expected, f"校验结果不符: {name}"

    def test_injection_attempts_are_rejected(self, engine):
        """防御：伪造超长/带符号的灵根名不能污染白名单。"""
        for bad in ["天灵根·火" * 10, "天灵根·火\n", "天灵根·火 ", "天灵根·火́", 12345]:
            assert not engine.is_valid_spirit_root(bad), f"未拦截: {bad!r}"

    def test_sanitize_drops_invalid_root(self, engine, base_state):
        """非法灵根在清洗时置空，下次 act 会自动重掷。"""
        for bad in ["天灵根·火火", "六灵根·伪灵根", "admin", "天灵根·金木水火土"]:
            s = engine.sanitize_state({**base_state, "spirit_root": bad})
            assert s["spirit_root"] == "", f"非法灵根未被清空: {bad}"


class TestFiveElements:
    def test_counter_cycle_is_consistent(self, engine):
        """金克木、木克土、土克水、水克火、火克金 —— 五步成环。"""
        chain = ["金", "木", "土", "水", "火"]
        for i, elem in enumerate(chain):
            assert engine.ELEMENT_COUNTER[elem] == chain[(i + 1) % 5]
        # 反查表必须与正表严格互逆
        for k, v in engine.ELEMENT_COUNTER.items():
            assert engine.ELEMENT_COUNTERED_BY[v] == k

    @pytest.mark.parametrize("root,enemy,expected", [
        ("天灵根·金", "木", 1.15),   # 克制
        ("单灵根·金", "火", 0.85),   # 被克
        ("单灵根·金", "土", 1.0),    # 无关
        ("四灵根·伪灵根", "木", 1.0),  # 伪灵根永不触发
        ("", "木", 1.0),              # 未测灵根
        ("天灵根·金", "", 1.0),       # 无属性敌人
    ])
    def test_multiplier_basic(self, engine, root, enemy, expected):
        assert engine.element_multiplier(root, enemy) == pytest.approx(expected)

    def test_multi_root_counter_takes_priority(self, engine):
        """多灵根元素多：克制优先于被克判定。"""
        # 水克火、火克金：root 含火与水，敌人火 → 先命中「水克火」?水是克火吗？
        # ELEMENT_COUNTER: 水→火, 所以水克火 → 玩家(水) 克制 敌(火) = 1.15
        assert engine.element_multiplier("双灵根·水火", "火") == pytest.approx(1.15)
        # 反过来：敌(is被克方)
        assert engine.element_multiplier("双灵根·金木", "火") == pytest.approx(0.85)  # 火克金

    def test_extract_elements(self, engine):
        assert engine.extract_elements("三灵根·金木水") == ["金", "木", "水"]
        assert engine.extract_elements("四灵根·伪灵根") == []
        assert engine.extract_elements("") == []
        assert engine.extract_elements("伪灵根") == []
        assert engine.extract_elements("三灵根·金木X") == ["金", "木"]  # 过滤非法字符


class TestRootCoefficients:
    @pytest.mark.parametrize("root,coeff,mod", [
        ("天灵根·火", 1.6, +0.10),
        ("单灵根·火", 1.3, +0.05),
        ("双灵根·金木", 1.1, +0.02),
        ("三灵根·金木水", 1.0, 0.0),
        ("四灵根·伪灵根", 0.75, -0.05),
        ("野鸡灵根·火", 1.0, 0.0),      # 未知按三灵根
        (None, 1.0, 0.0),
        ("", 1.0, 0.0),
    ])
    def test_info_lookup(self, engine, root, coeff, mod):
        assert engine.spirit_root_info(root) == (coeff, mod)

    def test_better_root_means_faster_growth(self, engine):
        """天灵根的成长必须真实强于伪灵根（否则天赋系统无意义）。"""
        _, c_best = engine.spirit_root_info("天灵根·火")[:1], None
        assert engine.grant_exp({"spirit_root": "天灵根·火"}, 100) == 160
        assert engine.grant_exp({"spirit_root": "四灵根·伪灵根"}, 100) == 75
        assert engine.grant_exp({"spirit_root": "天灵根·火"}, 100) > \
               engine.grant_exp({"spirit_root": "四灵根·伪灵根"}, 100)

    def test_negative_exp_is_not_amplified(self, engine):
        """惩罚不吃灵根加成 —— 否则差灵根会被双重惩罚。"""
        for root in ["天灵根·火", "四灵根·伪灵根", "三灵根·金木水", None]:
            assert engine.grant_exp({"spirit_root": root}, -30) == -30
        assert engine.grant_exp({"spirit_root": "天灵根·火"}, 0) == 0
