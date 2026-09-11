<script setup lang="ts">
/* 状态卡：境界/灵根/三围条/灵石/物品栏（数值全来自后端权威 state） */
import { computed } from "vue";
import { game, actions } from "../stores/game";
import { REALMS, EXP_MAX } from "../game/constants";

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

function pct(v: number, max: number) {
  return Math.max(0, Math.min(100, v / max * 100)) + "%";
}

function useItem(name: string) {
  actions.act({ type: "use_item", name });
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
    <div class="stat-foot">
      <span class="stones">灵石 <b id="stones">{{ game.state?.spirit_stones ?? 0 }}</b></span>
      <span id="items">
        <template v-if="!shownItems.length">
          <span class="item-empty">身无长物</span>
        </template>
        <template v-else>
          <button v-for="it in shownItems" :key="it.name" type="button" class="item-chip"
                  :title="'点击尝试服用 / 查看'" @click="useItem(it.name)">
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
