<script setup lang="ts">
/* 江湖人物详情卡（v3.13 · N1/N2/N3）：
   N1 档案：称谓、道缘条、结识轮次、结契、与 TA 相关的近事
   N2 主动操作：赠礼 / 论道 / 打听 / 切磋（bond 门槛 + 冷却明示）
   N3 结契：bond≥90 可结拜 / 师徒 / 道侣（每种契同时最多一人） */
import { computed } from "vue";
import { game, actions } from "../stores/game";
import type { NpcEntry } from "../game/types";

const props = defineProps<{ name: string }>();
const npc = computed<NpcEntry | undefined>(
  () => (game.state?.npcs || []).find(n => n.name === props.name),
);

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

const PACT_LABEL: Record<string, string> = { sworn: "结拜", master: "师徒", companion: "道侣" };
const PACT_DESC: Record<string, string> = {
  sworn: "歃血为盟 · 探索机缘掉率 +20%",
  master: "执弟子礼 · 修炼效率 +5%",
  companion: "互换信物 · 静养续命效果 +25%",
};

/* 相关近事：记忆里提到 TA（名字或曾用名）的条目 */
const memories = computed(() => {
  const aliases = new Set([npc.value?.name, ...(npc.value?.alias || [])].filter(Boolean));
  return (game.state?.memory || [])
    .filter(m => [...aliases].some(a => a && m.includes(a)))
    .slice(-4);
});

/* 冷却：还剩几轮能再来（读 op_cd） */
const COOLDOWNS: Record<string, number> = { gift: 3, talk: 5, ask: 5, spar: 3 };
const COOLDOWN_LABEL: Record<string, string> = {
  gift: "赠礼", talk: "论道", ask: "打听", spar: "切磋",
};
function cooldownLeft(op: string): number {
  const last = npc.value?.op_cd?.[op];
  if (last === undefined) return 0;
  return Math.max(0, last - (game.state?.turn ?? 0));
}

/* 操作可用性（把后端门槛在按钮上明示，避免点下去才被拒） */
const giftOk = computed(() => (npc.value?.bond ?? 0) >= -20);
const talkOk = computed(() => (npc.value?.bond ?? 0) >= 30);
const askOk = computed(() => (npc.value?.bond ?? 0) >= 20);
const sparOk = computed(() => (npc.value?.bond ?? 0) >= -20);
const pactOk = computed(() => (npc.value?.bond ?? 0) >= 90 && !npc.value?.pact);

function giftStones() {
  if (game.loading) return;
  actions.npcAct({ type: "npc_gift", name: props.name, stones: 30 });
}
function giftItem() {
  if (game.loading) return;
  // 从行囊挑一件可赠之物（丹药/材料皆可，取第一件）
  const it = (game.state?.items || [])[0];
  if (!it) { actions.floatText("行囊空空，无物可赠", "f-neg"); return; }
  actions.npcAct({ type: "npc_gift", name: props.name, item: it.name });
}
function doTalk() { actions.npcAct({ type: "npc_talk", name: props.name }); }
function doAsk() { actions.npcAct({ type: "npc_ask", name: props.name }); }
function doSpar() { actions.npcAct({ type: "npc_spar", name: props.name }); }
function doPact(ptype: string) {
  if (game.loading) return;
  actions.npcAct({ type: "npc_pact", name: props.name, pact: ptype });
}
function close() { game.npcDetail = null; }
</script>

<template>
  <div id="npc-detail" @click="close">
    <div class="sc-card nd-card" @click.stop v-if="npc">
      <div class="nd-head">
        <h3>{{ npc.name }}</h3>
        <span class="nd-title">{{ npc.title }}</span>
        <span v-if="npc.pact" class="nd-pact" :title="PACT_DESC[npc.pact.type]">
          {{ PACT_LABEL[npc.pact.type] || npc.pact.type }}
        </span>
      </div>

      <div class="nd-bond-row">
        <span class="nd-bond-label">{{ bondLabel(npc.bond) }}</span>
        <div class="nd-track"><i class="nd-fill" :class="{ neg: npc.bond < 0 }"
              :style="{ width: bondPct(npc.bond) }"></i></div>
        <span class="nd-bond-val" :class="{ neg: npc.bond < 0 }">{{ npc.bond }}</span>
      </div>
      <p class="sc-hint nd-met">初识于第 {{ (npc.met_turn ?? 0) + 1 }} 轮</p>

      <!-- 结契 buff 说明 -->
      <p v-if="npc.pact" class="nd-pact-note">{{ PACT_DESC[npc.pact.type] }}</p>

      <!-- N1：与 TA 相关的近事 -->
      <div class="nd-mem" v-if="memories.length">
        <div class="nd-sec">与 此 人 的 近 事</div>
        <div v-for="m in memories" :key="m" class="nd-mem-line">{{ m }}</div>
      </div>

      <!-- N2：主动操作 -->
      <div class="nd-sec">往 来</div>
      <div class="nd-ops">
        <button type="button" class="nd-op" :disabled="game.loading || !giftOk || cooldownLeft('gift') > 0"
                :title="giftOk ? '登门相赠，道缘 +（熟络后递减）' : '势同水火，礼下于人也无用'"
                @click="giftStones">
          赠灵石
          <small v-if="cooldownLeft('gift') > 0">{{ cooldownLeft('gift') }}轮</small>
        </button>
        <button type="button" class="nd-op" :disabled="game.loading || !giftOk || cooldownLeft('gift') > 0"
                title="以行囊之物相赠" @click="giftItem">赠物</button>
        <button type="button" class="nd-op" :disabled="game.loading || !talkOk || cooldownLeft('talk') > 0"
                :title="talkOk ? '坐而论道，得修为' : '交情未到，谁肯与你论道'"
                @click="doTalk">
          论道
          <small v-if="cooldownLeft('talk') > 0">{{ cooldownLeft('talk') }}轮</small>
        </button>
        <button type="button" class="nd-op" :disabled="game.loading || !askOk || cooldownLeft('ask') > 0"
                :title="askOk ? '探问消息，推进在册线索' : '交情未到，谁肯与你交底'"
                @click="doAsk">
          打听
          <small v-if="cooldownLeft('ask') > 0">{{ cooldownLeft('ask') }}轮</small>
        </button>
        <button type="button" class="nd-op" :disabled="game.loading || !sparOk || cooldownLeft('spar') > 0"
                :title="sparOk ? '点到为止的比试，胜则道缘渐深' : '仇深似海，见面就是生死斗'"
                @click="doSpar">
          切磋
          <small v-if="cooldownLeft('spar') > 0">{{ cooldownLeft('spar') }}轮</small>
        </button>
      </div>
      <p class="sc-warn nd-cd-tip">往来须耗时日，且同一人短时内不宜频访。</p>

      <!-- N3：结契 -->
      <div class="nd-sec">结 契 <span class="nd-sec-sub" v-if="npc.pact">已与 {{ npc.name }} 结{{ PACT_LABEL[npc.pact.type] }}</span></div>
      <div class="nd-ops nd-pacts" v-if="!npc.pact">
        <template v-if="pactOk">
          <button type="button" class="nd-op pact" :disabled="game.loading" title="歃血为盟 · 探索机缘掉率 +20%"
                  @click="doPact('sworn')">结拜</button>
          <button type="button" class="nd-op pact" :disabled="game.loading" title="执弟子礼 · 修炼效率 +5%"
                  @click="doPact('master')">师徒</button>
          <button type="button" class="nd-op pact" :disabled="game.loading" title="互换信物 · 静养续命效果 +25%"
                  @click="doPact('companion')">道侣</button>
        </template>
        <span v-else class="sc-hint nd-locked">道缘未至生死之交（需 90，现 {{ npc.bond }}），结契无从谈起</span>
      </div>

      <div class="sc-actions">
        <button type="button" class="sc-btn sc-close-btn" @click="close">告 辞</button>
      </div>
    </div>
  </div>
</template>
