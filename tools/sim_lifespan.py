# -*- coding: utf-8 -*-
"""《墨问仙途》时间 / 寿元 / 探索系统 · 蒙特卡洛仿真校验（v3 配平 · P0 + P1 + v3.1 地基修复）

对应《墨问仙途 下一版设计文档》的锚点：
    · 一次闭关均值 5 年（ACTION_DAYS["cultivate"] = (1260, 2340)，日效率 0.200）
    · 大境界修为需求 EXP_NEED = [4659, 8000, 10000, 8000]
    · 寿元：炼气 115~150 / 筑基 300~400；静养续命封顶 = 基础寿元的 12%
    · 探索三档 low(寻常走动) / mid(远行历练) / high(秘境探险)
    · 机缘物件：功法残卷/上古秘籍/仙家真诀 → 闭关效率；悟道石 → 突破率；护道符 → 免折损

v3.1 地基修复（本版新增，见 changes 清单 §二）：
    · FORTUNE_EXP 已清空 —— 奇遇不再即时给修为（非闭关行动脱离天数的 lump 全部砍掉）；
    · 灵丹改为「限时闭关效率 buff」（12 轮 +15%），掉落入背包、由玩家主动服用。
    仿真因此新增「贪心服丹」（持有即服），贴近真实玩法。

设计意图：探险不是「用时间换寿元」，而是「用风险换效率」——
纯闭关拿不到效率加成，探索流拿不到时间效率，两者必须取舍。

用法：
    python tools/sim_lifespan.py            # 默认 2000 次/策略
    python tools/sim_lifespan.py 20000      # 文档用的精度

⚠️ 仿真直接复用 server._postprocess_turn，因此不会与线上引擎漂移
（含探索掉落、机缘效率、闭门衰减、静养续命、寿元判定全都走真代码）。
任何参数改动，先跑这个脚本，再改 tests 里的断言。
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as E  # noqa: E402

# 炼气九层逐层需求之和 = EXP_NEED[0]（配平的分母）
QI_TOTAL = sum(r[1] for r in E.REALM_TABLE)


def _mix(period: int, offset: int, tier: str | None):
    """每 period 轮里，第 offset 轮出门（tier 为探索档位），其余闭关。"""
    return lambda t: ("explore", tier) if t % period == offset else ("cultivate", None)


STRATEGIES = {
    "闭关5+远行1":  _mix(6, 5, "mid"),
    "闭关5+秘境1":  _mix(6, 5, "high"),
    "纯闭关":       lambda t: ("cultivate", None),
    "远行探索流":   lambda t: ("explore", "mid"),
    "秘境探索流":   lambda t: ("explore", "high"),
    "修行5+静养1":  lambda t: ("rest", None) if t % 6 == 5 else ("cultivate", None),
    "静养为主":     lambda t: ("rest", None),
}


def fresh_state(seed_root: str = "三灵根·金木水") -> dict:
    return E.sanitize_state({"spirit_root": seed_root, "spirit_stones": 99999})


class _Req:
    """handle_use_elixir 只需要 last_choices（沿用上一轮选项），这里给个空壳。"""
    action: dict = {}
    last_choices = None


def _breakthrough(s: dict) -> str:
    """冲关：掷骰（含灵根修正、连败保底、悟道石加成）。
    返回 'done'（踏入筑基）/ 'ok'（层内升）/ 'fail'。"""
    rate, _ = E.breakthrough_rate(s)
    if random.random() >= rate:
        E.apply_trial(s, {"success": False})     # 护道符会在此免折损
        return "fail"
    if s["realm_index"] >= 8:
        E._ending_payload(s, "闭关冲关")          # 炼气 → 筑基：寿元重掷在此完成
        return "done"
    E.apply_trial(s, {"success": True})
    return "ok"


def run(strategy, max_turns: int = 4000) -> dict:
    """跑一局：炼气一层 → 筑基初期。返回统计量。

    v3.1：灵丹已改为「限时效率 buff」且入背包，故这里模拟**贪心服用**——
    持有即服（真实玩家的做法），buff 只在修行回合倒计时。
    """
    s = fresh_state()
    dead = False
    turns = 0
    elixirs = 0
    while turns < max_turns:
        if s.get("dead"):
            dead = True
            break
        # 圆满即冲关（先冲关再决定本轮的修行，避免白跑一轮）
        while s["realm_index"] < 9 and s["exp"] >= E.exp_max_of(s["realm_index"]):
            if _breakthrough(s) == "done":
                break
        if s["realm_index"] >= 9:
            break

        tag, tier = strategy(turns)
        turns += 1
        meta: dict = {}
        E._postprocess_turn(
            s, {"delta": {"exp": 0}, "choices": [], "narrative": "n", "memory": ""},
            meta, "行动", tag, risk_roll=0.0, tier=tier)
        # 贪心服丹：持有即服（只开限时效率 buff，不给裸修为）
        while (s.get("treasures") or {}).get("elixir"):
            if not E.handle_use_elixir(s, _Req()).get("ok"):
                break
            elixirs += 1
    treasures = sum((s.get("treasures") or {}).values())
    return {
        "turns": turns,
        "age": s["age"],
        "dead": dead or bool(s.get("dead")),
        "lifespan": s["lifespan"],
        "ratio": s["age"] / max(E.LIFESPAN_TABLE[0][1], 1),
        "elixirs": elixirs,
        "treasures": treasures,
        "eff_bonus": E.treasure_eff_bonus(s.get("treasures")),
        "realm": s["realm_index"],
        "won": (not dead) and s["realm_index"] >= 9,
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    random.seed(20260913)
    E._life_rng.seed(20260913)   # 寿元走独立随机流，也要一起播种才能复现
    qi_avg = (E.LIFESPAN_TABLE[0][1] + E.LIFESPAN_TABLE[0][2]) // 2
    print(f"炼气期总修为需求：{QI_TOTAL}（REALM_TABLE 九层之和；EXP_NEED[0] = {E.EXP_NEED[0]}）")
    print(f"一次闭关天数：{E.ACTION_DAYS['cultivate']}（均值 "
          f"{sum(E.ACTION_DAYS['cultivate']) / 2 / E.DAYS_PER_YEAR:.1f} 年）"
          f"　日效率 {E.DAY_EFF['cultivate']}")
    print(f"寿元：炼气 {E.LIFESPAN_TABLE[0][1]}~{E.LIFESPAN_TABLE[0][2]}（均值 {qi_avg}）"
          f"　安全线 {int(E.LIFESPAN_SAFE_RATIO * 100)}%　续命封顶 {E.REST_LIFE_BONUS_CAP:.0%}")
    print(f"每组 {n} 次\n")
    head = (f"{'策略':<16}{'轮数':>7}{'终局年龄':>9}{'死亡率':>8}"
            f"{'占寿元':>8}{'服丹':>6}{'物件':>6}{'效率':>7}{'入筑基':>8}")
    print(head)
    print("-" * len(head))
    for name, fn in STRATEGIES.items():
        rs = [run(fn) for _ in range(n)]
        avg = lambda k: sum(r[k] for r in rs) / n          # noqa: E731
        death = sum(1 for r in rs if r["dead"]) / n * 100
        win = sum(1 for r in rs if r["won"]) / n * 100
        print(f"{name:<16}{avg('turns'):>7.0f}{avg('age'):>9.0f}{death:>7.1f}%"
              f"{avg('ratio') * 100:>7.0f}%{avg('elixirs'):>6.1f}"
              f"{avg('treasures'):>6.1f}{avg('eff_bonus') * 100:>6.0f}%{win:>7.0f}%")
    print()
    print("死亡风险曲线（每轮，按炼气均寿元）：")
    for r in (0.60, 0.72, 0.80, 0.85, 0.90, 1.00, 1.05):
        print(f"  占寿元 {int(r * 100):>3}%  →  {E.death_risk(int(qi_avg * r), qi_avg) * 100:>5.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
