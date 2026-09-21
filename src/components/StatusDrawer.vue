<script setup lang="ts">
/* 全状态抽屉：点吸顶条唤起，底部滑出。
   三围/背包实时响应（用丹不关抽屉，连嗑），物品点击直接服用。 */
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { game } from "../stores/game";
import { REALMS, EXP_MAX, itemInfo, canUseItem, ageLevel, AGE_HINT, lifespanAvg } from "../game/constants";
import type { ThreadEntry } from "../game/types";

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
const age = computed(() => game.state?.age ?? 16);
const lifespan = computed(() => game.state?.lifespan ?? lifespanAvg(game.state?.realm_index ?? 0));
const ageLv = computed(() => ageLevel(age.value / Math.max(lifespan.value, 1)));
const agePctText = computed(() => Math.round(age.value / Math.max(lifespan.value, 1) * 100) + "%");
const ageHint = computed(() => AGE_HINT[ageLv.value] || "");
const npcs = computed(() => game.state?.npcs || []);

/* 未决之事：玩家自己也记不住追过几条线，看见了才知道该去收哪一条 */
const threads = computed(() => game.state?.threads || []);
const chronicle = computed(() => game.state?.chronicle || []);
function isOverdue(t: ThreadEntry): boolean {
  return (game.state?.turn ?? 0) > (t.due ?? 0);
}
function overdueRounds(t: ThreadEntry): number {
  return Math.max(0, (game.state?.turn ?? 0) - (t.due ?? 0));
}

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

/* 点道具先看详情（功效/说明），在弹窗里再决定服不服 —— 抽屉不关闭，可连着查看 */
function openItem(name: string) {
  if (game.loading) return;
  game.itemDetail = name;
}

function close() { game.statusDrawerOpen = false; }

/* ESC 也能收起：桌面上万一遮罩被内容盖住，键盘仍是保底出口 */
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && game.statusDrawerOpen) close();
}
if (typeof window !== "undefined") {
  window.addEventListener("keydown", onKeydown);
  onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
}

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

      <!-- 可滚动内容区：物品多/江湖人物多时，抽屉高度封顶、这里内部滚动。
           ⚠️ 没有它就会出「关不掉」的事故：抽屉原本是 absolute bottom:0 且无高度上限，
           内容撑爆后整块向上溢出视口，✕ 被顶出屏幕、遮罩也被完全盖住 —— 再也收不回来。 -->
      <div class="drawer-body">
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

      <div class="drawer-age" :class="'age-' + ageLv">
        <span class="da-label">寿 元</span>
        <span class="da-num">{{ age }} / {{ lifespan }} 岁</span>
        <span class="da-pct">{{ agePctText }}</span>
        <span class="da-hint">{{ ageHint || "来日方长" }}</span>
      </div>

      <div class="drawer-stones">灵石 <b>{{ game.state?.spirit_stones ?? 0 }}</b></div>

      <div class="drawer-items">
        <template v-if="(game.state?.items || []).length">
          <button v-for="it in game.state?.items" :key="it.name" type="button" class="item-chip"
                  :class="{ usable: canUseItem(it.name) }"
                  :title="`${itemInfo(it.name).effect}\n点击查看功效与说明`"
                  @click="openItem(it.name)">
            {{ it.name }}×{{ it.qty }}
          </button>
        </template>
        <span v-else class="item-empty">身无长物</span>
      </div>
      <p class="items-tip" v-if="(game.state?.items || []).length">
        朱红者可服用，点击任意一件查看功效 · 丹药按当前上限比例生效
      </p>

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

      <div class="drawer-threads" v-if="threads.length">
        <div class="dt-title">未 决 之 事 <span class="dt-count">{{ threads.length }}/3</span></div>
        <div v-for="t in threads" :key="t.title" class="thread-row" :class="{ overdue: isOverdue(t) }">
          <span class="th-cat">{{ t.cat || "疑窦" }}</span>
          <span class="th-title">{{ t.title }}</span>
          <span class="th-when">{{ isOverdue(t) ? "已逾期" + overdueRounds(t) + "轮"
            : "第" + (t.due ?? 0) + "轮前" }}</span>
          <span class="th-note" v-if="t.note">{{ t.note }}</span>
        </div>
      </div>

      <div class="drawer-chronicle" v-if="chronicle.length">
        <div class="dt-title">大 事 记</div>
        <div v-for="c in chronicle.slice(-4)" :key="c" class="chr-line">{{ c }}</div>
      </div>

      <div class="drawer-foot">
        <span>第 {{ turn + 1 }} 轮</span>
        <span v-if="summary" class="d-summary">前尘：{{ summary.slice(0, 26) }}{{ summary.length > 26 ? "…" : "" }}</span>
      </div>
      </div>
    </div>
  </div>
</template>
