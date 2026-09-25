<script setup lang="ts">
/* 选项区：常规选项 + 冲关金框 + 错误卡片（含重试）

   每个选项都带「行动类型」徽标：玩家在选之前就能看见选它会快还是慢，
   否则「选择决定节奏」这件事只存在于数值里，玩家感知不到。 */
import { game, actions } from "../stores/game";
import type { Choice } from "../game/types";
import { actionInfo, riskVolatility, exploreTierOfRisk, actionSpanHint, spanHint,
         CULTIVATE_SPAN, DEFAULT_CULTIVATE_SPAN, ACTION_DAYS } from "../game/constants";

function pick(c: Choice) {
  actions.act({
    type: c.special === "breakthrough" ? "breakthrough" : "choice",
    id: c.id, text: c.text, tag: c.tag,
    risk: c.risk,   // 探索档位由 risk 决定：low/mid/high → 寻常走动/远行历练/秘境探险
    short: c.short, // v3.1 兼容：片刻行功（周天/小坐）
    span: c.span,   // 修行粒度（short/medium/long）：不传则后端按整段闭关算，一次吃掉五年
  });
}

/** 本轮耗时区间：修行走 span 三档，其余走 ACTION_DAYS 表 */
function spanRange(c: Choice): [number, number] {
  if (c.tag === "cultivate") {
    return CULTIVATE_SPAN[c.span ?? ""] ?? CULTIVATE_SPAN[DEFAULT_CULTIVATE_SPAN];
  }
  return ACTION_DAYS[c.tag ?? ""] ?? ACTION_DAYS.other;
}

function riskCls(risk: string) {
  return risk === "low" ? "r-low" : risk === "high" ? "r-high" : "r-mid";
}

function riskTxt(c: Choice) {
  return c.special === "breakthrough" ? "冲关" :
    (c.risk === "low" ? "稳" : c.risk === "high" ? "险" : "常");
}

/** 行动徽标：冲关不参与修炼系数，不显示倍率；探索显示三档，其余按 tag 显示「修行 ×1.8」或「±40%」波动
 *
 *  tail 是「只留耗时」的那一半，供窄屏用：手机上「探索 · 」这三个字要吃掉
 *  约 42px，恰好是一句行动最后两三个字的位置——留着它，14 字的行动就会被
 *  挤成「……驿卜 / 三」。类型名在窄屏由颜色与句子本身承担。 */
function actBadge(c: Choice): { label: string; text: string; tail: string;
                                fast: boolean; volatile: boolean } {
  if (c.special === "breakthrough") {
    return { label: "冲关", text: "冲关", tail: "冲关", fast: false, volatile: false };
  }
  const info = actionInfo(c.tag);
  if (c.tag === "explore") {
    // 探索档位只看风险档：这决定了耗时、掉率与性命风险。
    // v3.4：徽标改摆时长（档位名仍在悬停里）——探索一档就是 25~60 天，
    // 只写「远行历练」，玩家点下去前根本不知道会被推进一个月。
    const tier = exploreTierOfRisk(c.risk);
    return { label: info.label, text: `探索 · ${spanHint(...tier.days)}`,
             tail: spanHint(...tier.days), fast: false, volatile: true };
  }
  // 其余一律把「要过多久」摆到台面上——点之前不知道是几天还是五年，是最伤的体感问题。
  // 修为按天产出，所以耗时即收益：看见「约5年」才明白这一下的分量。
  return {
    label: info.label,
    text: `${info.label} · ${actionSpanHint(c.tag, c.span)}`,
    tail: actionSpanHint(c.tag, c.span),
    fast: info.coeff > 1,
    volatile: riskVolatility(c.tag) > 0,
  };
}

/** 悬停说明：探索给档位取舍，其余给「行动说明 + 确切耗时」 */
function actTitle(c: Choice): string {
  if (c.tag === "explore" && c.special !== "breakthrough") {
    const t = exploreTierOfRisk(c.risk);
    const drop = t.drop > 0 ? `掉宝 ${Math.round(t.drop * 100)}%` : "无掉落";
    const risk = t.death > 0 ? `死亡率 ${(t.death * 100).toFixed(2)}%` : "几无凶险";
    return `${t.label}：${t.note}\n耗时 ${t.days[0]}~${t.days[1]} 天 · ${risk} · ${drop}`;
  }
  const info = actionInfo(c.tag);
  const [lo, hi] = spanRange(c);
  const tail = spanHint(lo, hi);
  if (c.tag === "cultivate") {
    const s = c.span && CULTIVATE_SPAN[c.span] ? c.span : DEFAULT_CULTIVATE_SPAN;
    const why = s === "short"
      ? "只耗一两天，故修为有限——但在闭关间隙攒连击很划算。"
      : s === "medium"
        ? "静修一月至数月：修为与寿元的中庸之选。"
        : "一次闭关跨数年：修为最丰，寿元也耗得最狠。";
    return `${info.note}\n耗时 ${lo}~${hi} 天（${tail}）——${why}`;
  }
  return `${info.note}\n耗时 ${lo}~${hi} 天（${tail}）`;
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
          <span v-if="c.hint" class="chint">{{ c.hint }}</span>
        </span>
        <!-- 徽标是「标签」，不该跟行动句子抢同一行：留在文字流里时，
             一句 14 字的行动就会被它顶到第二行——手机上一整列选项
             全是两行，根因就在这。挪出来当按钮的独立一列后，
             短行动一行放得下，长行动也折得整齐。 -->
        <span v-if="c.special !== 'breakthrough'" class="ctag"
              :class="[actBadge(c).fast ? 'tag-fast' : 'tag-slow', actBadge(c).volatile ? 'tag-vol' : '']"
              :title="actTitle(c)">
          <span class="ctag-kind">{{ actBadge(c).label }} · </span>{{ actBadge(c).tail }}
        </span>
        <span v-if="c.tag === 'fight'" class="fx-badge" title="斗法">⚔</span>
        <span class="risk" :class="riskCls(c.risk)">{{ riskTxt(c) }}</span>
      </button>
    </template>
  </div>
</template>
