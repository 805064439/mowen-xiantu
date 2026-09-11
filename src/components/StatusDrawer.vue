<script setup lang="ts">
/* 全状态抽屉：点吸顶条唤起，底部滑出。
   三围/背包实时响应（用丹不关抽屉，连嗑），物品点击直接服用。 */
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { game, actions } from "../stores/game";
import { REALMS, EXP_MAX } from "../game/constants";

const realm = computed(() => REALMS[game.state?.realm_index ?? 0]);
const root = computed(() => game.state?.spirit_root || "");
const expMax = computed(() => EXP_MAX[game.state?.realm_index ?? 0]);
const full = computed(() => (game.state?.realm_index ?? 0) < 9 && (game.state?.exp ?? 0) >= expMax.value);
const realmFullText = computed(() =>
  full.value ? "圆满 · 可冲关" : ((game.state?.realm_index ?? 0) === 9 ? "第一章 · 已筑基" : ""));

const bars = computed(() => {
  const s = game.state;
  if (!s) return [];
  return [
    { id: "bar-hp", label: "气血", val: s.hp, max: s.hp_max, glow: false },
    { id: "bar-qi", label: "灵力", val: s.qi, max: s.qi_max, glow: false },
    { id: "bar-exp", label: "修为", val: s.exp, max: expMax.value, glow: full.value },
  ];
});

const summary = computed(() => game.state?.memory_summary || "");
const turn = computed(() => game.state?.turn ?? 0);
const npcs = computed(() => game.state?.npcs || []);

/** 道缘数值 → 称谓（与后端 bond_label 同语义） */
function bondLabel(bond: number): string {
  if (bond <= -60) return "死敌";
  if (bond <= -20) return "敌视";
  if (bond < 20) return "相识";
  if (bond < 50) return "友善";
  if (bond < 80) return "亲近";
  return "生死之交";
}
function bondPct(bond: number): string {
  return Math.max(0, Math.min(100, (bond + 100) / 2)) + "%";
}

function pct(v: number, max: number) {
  return Math.max(0, Math.min(100, v / max * 100)) + "%";
}

function useItem(name: string) {
  if (game.loading) return;
  actions.act({ type: "use_item", name });
}

function close() { game.statusDrawerOpen = false; }

/* 下滑手势关闭（拖动区） */
const dragY = ref<number | null>(null);
function onTouchStart(e: TouchEvent) { dragY.value = e.touches[0].clientY; }
function onTouchMove(e: TouchEvent) {
  if (dragY.value === null) return;
  const dy = e.touches[0].clientY - dragY.value;
  if (dy > 60) { dragY.value = null; close(); }
}
function onTouchEnd() { dragY.value = null; }

/* 滚动锁跟随抽屉开合：开 → 锁 body；关 → 解锁。
   （组件常驻挂载，锁不能绑在 onMounted/onBeforeUnmount 上，
    否则页面一加载就被锁死且永不解除） */
watch(() => game.statusDrawerOpen, (open) => {
  document.body.classList.toggle("no-scroll", open);
}, { immediate: true });
onBeforeUnmount(() => document.body.classList.remove("no-scroll"));
</script>

<template>
  <div v-if="game.statusDrawerOpen" class="drawer-mask" @click="close">
    <div class="drawer" role="dialog" aria-label="完整状态" @click.stop>
      <div class="drawer-grip" @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd"
           @click="close" title="下滑或点击收起"></div>

      <button type="button" class="drawer-close" aria-label="收起状态面板" title="收起" @click="close">✕</button>

      <div class="drawer-head">
        <span class="d-realm">{{ realm }}</span>
        <span class="d-root" :class="{ heaven: root.startsWith('天灵根') }">{{ root }}</span>
        <span class="d-full" v-if="realmFullText">{{ realmFullText }}</span>
      </div>

      <div class="drawer-bars">
        <div v-for="b in bars" :key="b.id" class="bar-row" :id="'d-' + b.id"
             :class="{ 'exp-full': b.glow && b.id === 'bar-exp' }">
          <span class="bar-label">{{ b.label }}</span>
          <div class="bar-track"><div class="bar-fill" :style="{ width: pct(b.val, b.max) }"></div></div>
          <span class="bar-val">{{ b.val }}/{{ b.max }}</span>
        </div>
      </div>

      <div class="drawer-stones">灵石 <b>{{ game.state?.spirit_stones ?? 0 }}</b></div>

      <div class="drawer-items">
        <template v-if="(game.state?.items || []).length">
          <button v-for="it in game.state?.items" :key="it.name" type="button" class="item-chip"
                  :disabled="game.loading" title="点击尝试服用 / 查看" @click="useItem(it.name)">
            {{ it.name }}×{{ it.qty }}
          </button>
        </template>
        <span v-else class="item-empty">身无长物</span>
      </div>

      <div class="drawer-npcs" v-if="npcs.length">
        <div class="dn-title">江 湖 人 物</div>
        <div v-for="n in npcs" :key="n.name" class="npc-row">
          <span class="npc-name">{{ n.name }}</span>
          <span class="npc-title">{{ n.title }}</span>
          <span class="npc-track"><i class="npc-fill" :class="{ neg: n.bond < 0 }"
                :style="{ width: bondPct(n.bond) }"></i></span>
          <span class="npc-bond" :class="{ neg: n.bond < 0 }">{{ bondLabel(n.bond) }}</span>
        </div>
      </div>

      <div class="drawer-foot">
        <span>第 {{ turn + 1 }} 轮</span>
        <span v-if="summary" class="d-summary">前尘：{{ summary.slice(0, 26) }}{{ summary.length > 26 ? "…" : "" }}</span>
      </div>
    </div>
  </div>
</template>
