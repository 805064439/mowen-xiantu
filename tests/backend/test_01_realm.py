# -*- coding: utf-8 -*-
"""境界体系：名称映射、气血/灵力成长曲线、修为上限。

后端是数值的唯一权威，任何一处曲线被改都会直接影响平衡，
所以这里既测「当前值正确性」，也测「结构性约束」（单调性、可达性）。
"""
import pytest


class TestRealmTable:
    def test_table_shape(self, engine):
        """境界表必须 9 层，每项 (名称, 所需修为, 冲关率)。"""
        assert len(engine.REALM_TABLE) == 9
        for row in engine.REALM_TABLE:
            assert len(row) == 3
            name, exp_req, rate = row
            assert isinstance(name, str) and name.startswith("炼气")
            assert 0 < exp_req
            assert 0 < rate <= 1.0

    def test_realm_name_in_and_out_of_range(self, engine):
        for i in range(9):
            assert engine.realm_name(i) == engine.REALM_TABLE[i][0]
        # 越界一律筑基
        assert engine.realm_name(9) == engine.FOUNDATION == "筑基初期"
        assert engine.realm_name(99) == "筑基初期"

    def test_exp_curve_is_monotonic_increasing(self, engine):
        """修为需求必须逐层递增 —— 防止某一层出现「回头 concave」的低级错误。"""
        exps = [row[1] for row in engine.REALM_TABLE]
        assert exps == sorted(exps), f"修为需求非单调: {exps}"
        assert all(b > a for a, b in zip(exps, exps[1:])), "存在相邻层修为需求持平"

    def test_difficulty_walls_exist(self, engine):
        """设计文档声明的壁障：3→4 层与 6→7 层成功率骤降，9 层冲筑基最难。"""
        rates = [row[2] for row in engine.REALM_TABLE]
        assert rates[3] < rates[2] - 0.1, "三层→四层应为第一壁障"
        assert rates[6] < rates[5] - 0.1, "六层→七层应为第二壁障"
        assert min(rates) == rates[8], "九层冲筑基应为全局最难关"
        assert rates[8] <= 0.3

    def test_first_layer_is_forgiving(self, engine):
        """新手起步必须宽松，否则开局即劝退。"""
        assert engine.REALM_TABLE[0][2] >= 0.9


class TestGrowthCurves:
    def test_initial_values(self, engine):
        assert engine.hp_max_of(0) == 100
        assert engine.qi_max_of(0) == 50

    def test_hp_growth_matches_gain_table(self, engine):
        """逐层累加：hp_max(i+1) - hp_max(i) 必须等于 HP_GAINS[i]。"""
        for i in range(9):
            delta = engine.hp_max_of(i + 1) - engine.hp_max_of(i)
            expected = engine.HP_GAINS[i] if i < len(engine.HP_GAINS) else 10
            assert delta == expected, f"第{i}层气血成长异常"

    def test_qi_growth_matches_gain_table(self, engine):
        for i in range(9):
            delta = engine.qi_max_of(i + 1) - engine.qi_max_of(i)
            expected = engine.QI_GAINS[i] if i < len(engine.QI_GAINS) else 5
            assert delta == expected, f"第{i}层灵力成长异常"

    def test_curves_are_strictly_increasing(self, engine):
        hp = [engine.hp_max_of(i) for i in range(10)]
        qi = [engine.qi_max_of(i) for i in range(10)]
        assert hp == sorted(hp) and len(set(hp)) == len(hp)
        assert qi == sorted(qi) and len(set(qi)) == len(qi)

    def test_max_realm(self, engine):
        assert engine.MAX_REALM_INDEX == 9
        assert engine.exp_max_of(9) == 9999

    @pytest.mark.parametrize("idx", list(range(10)))
    def test_gain_tables_cover_all_layers(self, engine, idx):
        """HP_GAINS/QI_GAINS 长度必须覆盖全部 9 次进阶，否则会静默走默认值。"""
        assert len(engine.HP_GAINS) == 9
        assert len(engine.QI_GAINS) == 9
        assert engine.hp_max_of(idx) > 0 and engine.qi_max_of(idx) > 0
