<script setup lang="ts">
/* 状态卡：境界/灵根/三围条/灵石/物品栏（数值全来自后端权威 state） */
import { computed } from "vue";
import { game, actions } from "../stores/game";
import {
  REALMS, EXP_MAX, itemInfo, canUseItem,
  actionInfo, streakCoeff, seclusionCoeff, STREAK_CAP, SECLUSION_STREAK,
} from "../game/constants";

const realm = computed(() => REALMS[game.state?.realm_index ?? 0]);
const root = computed(() => game.state?.spirit_root || "");
const isHeaven = computed(() => root.value.startsWith("天灵根"));
const full = computed(() => {
  const lv = game.state?.realm_index ?? 0;
  return lv < 9 && (game.state?.exp ?? 0) >= EXP_MAX[lv];
});
const realmFullText = computed(() =>
  full.value ? "圆满 · 可冲关" : ((game.state?.realm_index ?? 0) === 9 ? "第一章 · 已筑基" : ""));

const bars = computed(() => {
  const s = game.state;
  if (!s) return [];
  return [
    { id: "bar-hp", label: "气血", val: s.hp, max: s.hp_max, extra: false },
    { id: "bar-qi", label: "灵力", val: s.qi, max: s.qi_max, extra: false },
    { id: "bar-exp", label: "修为", val: s.exp, max: EXP_MAX[s.realm_index], extra: full.value },
  ];
});

const shownItems = computed(() => (game.state?.items || []).slice(0, 8));
const overflow = computed(() => {
  const n = (game.state?.items || []).length;
  return n > 8 ? n : 0;
});

/* 江湖人物摘要：主面板前 3 个，更多进抽屉 */
const shownNpcs = computed(() => (game.state?.npcs || []).slice(0, 3));
const npcOverflow = computed(() => Math.max(0, (game.state?.npcs || []).length - 3));

/* 修行节奏：把「速度」摆在玩家眼前 —— 这是本次优化的核心可感知点。
   连修加成、闭门衰减、上一轮的行动与系数，三者合起来解释「我为什么快/慢」。 */
const streak = computed(() => game.state?.cultivate_streak ?? 0);
const streakPct = computed(() => Math.round((streakCoeff(streak.value) - 1) * 100));
const secluded = computed(() => streak.value >= SECLUSION_STREAK);
const seclusionLoss = computed(() =>
  secluded.value ? Math.round((1 - seclusionCoeff(streak.value)) * 100) : 0);
const lastCultivate = computed(() => game.lastMeta?.cultivate ?? null);
const lastAction = computed(() => {
  const c = lastCultivate.value;
  return c ? actionInfo(c.action) : null;
});
const coeffTitle = computed(() => {
  const c = lastCultivate.value;
  if (!c) return "";
  return `本轮修为 = ${c.base ?? "?"}（基础） × ${c.coeff}（灵根·行动·连击·状态）`;
});

function pct(v: number, max: number) {
  return Math.max(0, Math.min(100, v / max * 100)) + "%";
}

/* 点道具不再直接服用：先看详情（功效/说明），在弹窗里再决定服不服 */
function openItem(name: string) {
  game.itemDetail = name;
}

function openDrawer() {
  game.statusDrawerOpen = true;
}
</script>

<template>
  <section id="status">
    <div v-for="b in bars" :key="b.id" class="bar-row" :id="b.id" :class="{ 'exp-full': b.extra && b.id === 'bar-exp' }">
      <span class="bar-label">{{ b.label }}</span>
      <div class="bar-track"><div class="bar-fill" :style="{ width: pct(b.val, b.max) }"></div></div>
      <span class="bar-val">{{ b.val }}/{{ b.max }}</span>
    </div>
    <div class="stat-cult" :class="{ 'cult-secluded': secluded }" v-if="game.state">
      <span class="cult-label">修 行</span>
      <template v-if="secluded">
        <span class="cult-warn">闭门造车 · 进境 −{{ seclusionLoss }}%</span>
        <span class="cult-tip">出门走动一轮即可恢复</span>
      </template>
      <template v-else-if="streak > 0">
        <span class="cult-on">连修 {{ Math.min(streak, STREAK_CAP) }} 轮</span>
        <span class="cult-bonus" v-if="streakPct > 0">+{{ streakPct }}%</span>
        <span class="cult-tip" v-else>再连修一轮起有加成</span>
      </template>
      <template v-else>
        <span class="cult-off">未修行</span>
        <span class="cult-tip" v-if="lastAction">
          上轮「{{ lastAction.label }}」 {{ lastAction.coeff >= 1 ? "+" : "" }}{{ Math.round((lastAction.coeff - 1) * 100) }}% 修为
        </span>
      </template>
      <span class="cult-coeff" v-if="lastCultivate" :title="coeffTitle">
        ×{{ lastCultivate.coeff }}
      </span>
    </div>

    <div class="stat-foot">
      <span class="stones">灵石 <b id="stones">{{ game.state?.spirit_stones ?? 0 }}</b></span>
      <span id="items">
        <template v-if="!shownItems.length">
          <span class="item-empty">身无长物</span>
        </template>
        <template v-else>
          <button v-for="it in shownItems" :key="it.name" type="button" class="item-chip"
                  :class="{ usable: canUseItem(it.name) }"
                  :title="`${itemInfo(it.name).effect}\n点击查看功效与说明`"
                  @click="openItem(it.name)">
            {{ it.name }}×{{ it.qty }}
          </button>
          <span v-if="overflow" class="item-empty">…等{{ overflow }}件</span>
        </template>
      </span>
    </div>

    <div class="stat-npcs" v-if="shownNpcs.length">
      <span class="npcs-label">江 湖</span>
      <button v-for="n in shownNpcs" :key="n.name" type="button" class="npc-chip"
              :class="{ neg: n.bond < 0 }" :title="`${n.title} · ${n.bond > 0 ? '善' : n.bond < 0 ? '恶' : '中立'}（${n.bond}）\n点击查看完整江湖人物`"
              @click="openDrawer">
        <i class="npc-dot"></i>{{ n.name }}
      </button>
      <button v-if="npcOverflow" type="button" class="npc-more" @click="openDrawer"
              :title="`还有 ${npcOverflow} 位江湖人物`">…等{{ npcOverflow }}人</button>
    </div>
  </section>
</template>
