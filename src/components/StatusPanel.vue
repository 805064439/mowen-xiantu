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

function pct(v: number, max: number) {
  return Math.max(0, Math.min(100, v / max * 100)) + "%";
}

function useItem(name: string) {
  actions.act({ type: "use_item", name });
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
  </section>
</template>
