<script setup lang="ts">
/* 吸顶迷你状态条：原状态卡滚出视口后 fixed 吸顶常驻，
   点击任意处唤起全状态抽屉。回顶部时淡出，两态互斥。 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue";
import { game } from "../stores/game";
import { REALMS, EXP_MAX, ageLevel, lifespanAvg } from "../game/constants";

const visible = ref(false);
let observer: IntersectionObserver | null = null;
let statusEl: Element | null = null;

const realm = computed(() => REALMS[game.state?.realm_index ?? 0]);
const root = computed(() => game.state?.spirit_root || "");
const expMax = computed(() => EXP_MAX[game.state?.realm_index ?? 0]);
const expFull = computed(() => (game.state?.realm_index ?? 0) < 9 && (game.state?.exp ?? 0) >= expMax.value);
const hpLow = computed(() => (game.state?.hp ?? 100) > 0 && (game.state?.hp ?? 0) / (game.state?.hp_max || 1) < 0.3);
/* 年岁：安全线内只作低调陪衬，越线才吃色——避免无谓的焦虑噪音 */
const age = computed(() => game.state?.age ?? 16);
const lifespan = computed(() => game.state?.lifespan ?? lifespanAvg(game.state?.realm_index ?? 0));
const ageLv = computed(() => ageLevel(age.value / Math.max(lifespan.value, 1)));

const minis = computed(() => {
  const s = game.state;
  if (!s) return [];
  return [
    { key: "hp", label: "♥", val: s.hp, max: s.hp_max },
    { key: "qi", label: "⚡", val: s.qi, max: s.qi_max },
    { key: "exp", label: "▣", val: s.exp, max: expMax.value },
  ];
});

function pct(v: number, max: number) {
  return Math.max(0, Math.min(100, v / max * 100)) + "%";
}

function openDrawer() {
  game.statusDrawerOpen = true;
}

onMounted(async () => {
  await nextTick();
  statusEl = document.querySelector("#status");
  if (!statusEl) return;
  observer = new IntersectionObserver(
    ([entry]) => { visible.value = !entry.isIntersecting; },
    { rootMargin: "-1px 0px 0px 0px", threshold: 0 },
  );
  observer.observe(statusEl);
});

onBeforeUnmount(() => {
  observer?.disconnect();
  observer = null;
});
</script>

<template>
  <div id="sticky-bar" :class="{ on: visible }" role="button" tabindex="0"
       aria-label="查看完整状态" @click="openDrawer" @keydown.enter="openDrawer">
    <div class="sb-row">
      <span class="sb-realm">{{ realm }}</span>
      <span class="sb-root" :class="{ heaven: root.startsWith('天灵根') }">{{ root }}</span>
      <span class="sb-age" :class="'age-' + ageLv"
            :title="`年岁 ${age} / 寿元 ${lifespan}`">{{ age }}岁</span>
      <span class="sb-stones">◈ {{ game.state?.spirit_stones ?? 0 }}</span>
    </div>
    <div class="sb-row sb-bars">
      <div v-for="m in minis" :key="m.key" class="sb-mini"
           :class="{ 'sb-exp-full': m.key === 'exp' && expFull, 'sb-hp-low': m.key === 'hp' && hpLow }">
        <span class="sb-sym">{{ m.label }}</span>
        <span class="sb-track"><span class="sb-fill" :style="{ width: pct(m.val, m.max) }"></span></span>
      </div>
      <span class="sb-more">⌃</span>
    </div>
  </div>
</template>
