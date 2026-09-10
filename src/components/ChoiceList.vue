<script setup lang="ts">
/* 选项区：常规选项 + 冲关金框 + 错误卡片（含重试） */
import { game, actions } from "../stores/game";
import type { Choice } from "../game/types";

function pick(c: Choice) {
  actions.act({
    type: c.special === "breakthrough" ? "breakthrough" : "choice",
    id: c.id, text: c.text,
  });
}

function riskCls(risk: string) {
  return risk === "low" ? "r-low" : risk === "high" ? "r-high" : "r-mid";
}

function riskTxt(c: Choice) {
  return c.special === "breakthrough" ? "冲关" :
    (c.risk === "low" ? "稳" : c.risk === "high" ? "险" : "常");
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
              :class="{ gold: c.special === 'breakthrough' }"
              :disabled="game.inputLocked" @click="pick(c)">
        <span class="cid">{{ c.id || "·" }}</span>
        <span class="ctext">{{ c.text }}</span>
        <span class="risk" :class="riskCls(c.risk)">{{ riskTxt(c) }}</span>
      </button>
    </template>
  </div>
</template>
