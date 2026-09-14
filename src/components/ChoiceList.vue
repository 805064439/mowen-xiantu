<script setup lang="ts">
/* 选项区：常规选项 + 冲关金框 + 错误卡片（含重试）

   每个选项都带「行动类型」徽标：玩家在选之前就能看见选它会快还是慢，
   否则「选择决定节奏」这件事只存在于数值里，玩家感知不到。 */
import { game, actions } from "../stores/game";
import type { Choice } from "../game/types";
import { actionInfo, riskVolatility, exploreTierOfRisk } from "../game/constants";

function pick(c: Choice) {
  actions.act({
    type: c.special === "breakthrough" ? "breakthrough" : "choice",
    id: c.id, text: c.text, tag: c.tag,
    risk: c.risk,   // 探索档位由 risk 决定：low/mid/high → 寻常走动/远行历练/秘境探险
  });
}

function riskCls(risk: string) {
  return risk === "low" ? "r-low" : risk === "high" ? "r-high" : "r-mid";
}

function riskTxt(c: Choice) {
  return c.special === "breakthrough" ? "冲关" :
    (c.risk === "low" ? "稳" : c.risk === "high" ? "险" : "常");
}

/** 行动徽标：冲关不参与修炼系数，不显示倍率；探索显示三档，其余按 tag 显示「修行 ×1.8」或「±40%」波动 */
function actBadge(c: Choice): { label: string; text: string; fast: boolean; volatile: boolean } {
  if (c.special === "breakthrough") return { label: "冲关", text: "冲关", fast: false, volatile: false };
  const info = actionInfo(c.tag);
  if (c.tag === "explore") {
    // 探索档位只看风险档：这决定了耗时、掉率与性命风险
    const tier = exploreTierOfRisk(c.risk);
    return { label: info.label, text: `探索 · ${tier.label}`, fast: false, volatile: true };
  }
  const vol = riskVolatility(c.tag);
  if (vol > 0) {
    return {
      label: info.label,
      text: `${info.label} ±${Math.round(vol * 100)}%`,
      fast: info.coeff > 1,
      volatile: true,
    };
  }
  const sign = info.coeff >= 1 ? "+" : "";
  return {
    label: info.label,
    text: `${info.label} ${sign}${Math.round((info.coeff - 1) * 100)}%`,
    fast: info.coeff > 1,
    volatile: false,
  };
}

/** 悬停说明：探索给出档位取舍，其余给行动说明 */
function actTitle(c: Choice): string {
  if (c.tag === "explore" && c.special !== "breakthrough") {
    const t = exploreTierOfRisk(c.risk);
    const drop = t.drop > 0 ? `掉宝 ${Math.round(t.drop * 100)}%` : "无掉落";
    const risk = t.death > 0 ? `死亡率 ${(t.death * 100).toFixed(2)}%` : "几无凶险";
    return `${t.label}：${t.note}\n耗时 ${t.days[0]}~${t.days[1]} 天 · ${risk} · ${drop}`;
  }
  return actionInfo(c.tag).note;
}

function retry() {
  if (game.errorCard) actions.act(game.errorCard.action);
}
</script>

<template>
  <div id="choices" :style="{ opacity: game.loading ? '.45' : '' }">
    <template v-if="game.errorCard">
      <div class="error-card">
        天机紊乱，一时推演不出后事。（{{ game.errorCard.message }}）
      </div>
      <button type="button" class="choice retry" @click="retry">
        <span class="cid">↻</span><span class="ctext">凝神再试</span>
      </button>
    </template>
    <template v-else>
      <button v-for="c in game.choices" :key="c.id" type="button" class="choice"
              :class="{ gold: c.special === 'breakthrough', battle: c.tag === 'fight' }"
              :disabled="game.inputLocked" @click="pick(c)">
        <span class="cid">{{ c.id || "·" }}</span>
        <span class="ctext">
          {{ c.text }}
          <span v-if="c.special !== 'breakthrough'" class="ctag"
                :class="[actBadge(c).fast ? 'tag-fast' : 'tag-slow', actBadge(c).volatile ? 'tag-vol' : '']"
                :title="actTitle(c)">
            {{ actBadge(c).text }}
          </span>
          <span v-if="c.hint" class="chint">{{ c.hint }}</span>
        </span>
        <span v-if="c.tag === 'fight'" class="fx-badge" title="斗法">⚔</span>
        <span class="risk" :class="riskCls(c.risk)">{{ riskTxt(c) }}</span>
      </button>
    </template>
  </div>
</template>
