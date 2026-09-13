# -*- coding: utf-8 -*-
"""《墨问仙途》时间/寿元系统 · 蒙特卡洛仿真校验

对应《时间/寿元系统 最终配平方案 v2》§3 的锚点。任何参数改动请先跑这个脚本，
确认锚点没跑飞再上线（建议接 CI 做数值回归）。

用法：
    python tools/sim_lifespan.py            # 默认 2000 次/策略
    python tools/sim_lifespan.py 20000      # 文档用的精度

锚点（v2 §6）：
    闭关 5 + 探索 1  →  68 轮 / 102 岁 / 0.1% 死亡
    纯闭关          →  84 轮 / 142 岁 / 29%  死亡
    探索流          → 112 轮 /  19 岁 / 0%   死亡
    静养流（续命后）→   不死
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server as E  # noqa: E402

# 炼气期一层层爬完所需的总修为（REALM_TABLE 九层之和 = 3450 = EXP_NEED[0]）
QI_TOTAL = sum(r[1] for r in E.REALM_TABLE)
EXP_MAX_BY_LEVEL = [r[1] for r in E.REALM_TABLE]

STRATEGIES = {
    "闭关5+探索1": lambda t: "explore" if t % 6 == 5 else "cultivate",
    "闭关3+探索1": lambda t: "explore" if t % 4 == 3 else "cultivate",
    "纯闭关":      lambda t: "cultivate",
    "探索为主":    lambda t: "explore",
    "静养为主":    lambda t: "rest",
    "张弛有度(5+静养1)": lambda t: "rest" if t % 6 == 5 else "cultivate",
}


def fresh_state(seed_root: str = "三灵根·金木水") -> dict:
    s = E.sanitize_state({})
    s["spirit_root"] = seed_root
    return s


def run(strategy, max_turns: int = 4000) -> dict:
    """跑一局：从炼气一层爬到炼气九层圆满（第一章终点前）。"""
    s = fresh_state()
    age, dead, turns = E.START_AGE, False, 0
    fortunes = 0
    for t in range(max_turns):
        tag = strategy(t)
        exp, days, fortune = E.action_exp(tag)
        if fortune:
            fortunes += 1
        coeff = E.time_exp_coeff(s, tag, 0.0)
        gain = int(exp * coeff)
        cap = max(1, int(E.exp_max_of(s["realm_index"]) * E.SINGLE_TURN_EXP_CAP))
        gain = min(gain, cap)
        s["exp"] += gain
        # 逐层突破（成功率取 breakthrough_rate：含灵根修正与连败保底，失败保留 70%~85% 修为）
        while s["realm_index"] < 8 and s["exp"] >= E.exp_max_of(s["realm_index"]):
            rate, _ = E.breakthrough_rate(s)
            if random.random() < rate:
                s["realm_index"] += 1
                s["exp"] = 0
                s["fail_streak"] = 0
            else:
                fs = s.get("fail_streak", 0)
                s["exp"] = int(s["exp"] * (0.70 + min(fs * 0.05, 0.15)))
                s["fail_streak"] = fs + 1
                break
        E._update_cultivate_streak(s, tag)
        s["days"] += days
        s["age"] = E.START_AGE + s["days"] // E.DAYS_PER_YEAR
        if tag == "rest":
            s["rest_count"] += 1
            if s["rest_count"] % E.REST_LIFE_BONUS_EVERY == 0:
                bn = s["life_bonus"]
                nn = min(bn + E.REST_LIFE_BONUS, E.REST_LIFE_BONUS_CAP)
                g = int(nn) - int(bn)
                s["life_bonus"] = round(nn, 1)
                s["lifespan"] += g
        turns = t + 1
        if s["realm_index"] >= 8 and s["exp"] >= E.exp_max_of(8):
            break
        if E.check_lifespan_death(s):
            dead = True
            break
    return {
        "turns": turns,
        "age": s["age"],
        "dead": dead,
        "lifespan": s["lifespan"],
        "ratio": s["age"] / max(s["lifespan"], 1),
        "fortunes": fortunes,
        "won": (not dead) and s["realm_index"] >= 8,
    }


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    random.seed(20260913)
    E._life_rng.seed(20260913)   # 寿元走独立随机流，也要一起播种才能复现
    print(f"炼气期总修为需求：{QI_TOTAL}（REALM_TABLE 九层之和；EXP_NEED[0] = {E.EXP_NEED[0]}）")
    print(f"寿元：炼气期 {E.LIFESPAN_TABLE[0][1]}~{E.LIFESPAN_TABLE[0][2]}"
          f"（均值 {(E.LIFESPAN_TABLE[0][1] + E.LIFESPAN_TABLE[0][2]) // 2}）"
          f"　安全线 {int(E.LIFESPAN_SAFE_RATIO * 100)}%")
    print(f"每组 {n} 次\n")
    head = f"{'策略':<18}{'轮数':>8}{'终局年龄':>10}{'死亡率':>10}{'占寿元':>10}{'奇遇':>8}"
    print(head)
    print("-" * len(head))
    for name, fn in STRATEGIES.items():
        rs = [run(fn) for _ in range(n)]
        avg_turns = sum(r["turns"] for r in rs) / n
        alive = [r for r in rs if not r["dead"]]
        avg_age = sum(r["age"] for r in rs) / n
        death = sum(1 for r in rs if r["dead"]) / n * 100
        ratio = sum(r["ratio"] for r in rs) / n * 100
        fort = sum(r["fortunes"] for r in rs) / n
        print(f"{name:<18}{avg_turns:>8.0f}{avg_age:>10.0f}{death:>9.1f}%{ratio:>9.0f}%{fort:>8.1f}")
    print()
    print("死亡风险曲线（每轮）：")
    for r in (0.60, 0.72, 0.80, 0.85, 0.90, 1.00, 1.05):
        print(f"  占寿元 {int(r * 100):>3}%  →  {E.death_risk(int(165 * r), 165) * 100:>5.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
