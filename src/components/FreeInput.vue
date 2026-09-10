<script setup lang="ts">
/* 自由输入：任意行动 + 最近 5 条历史（datalist） */
import { ref, watch } from "vue";
import { game, actions } from "../stores/game";
import { loadHistory, pushHistory } from "../game/storage";

const text = ref("");
const history = ref<string[]>(loadHistory());
const inputEl = ref<HTMLInputElement | null>(null);

function submit() {
  const t = text.value.trim();
  if (!t || game.loading) return;
  text.value = "";
  history.value = pushHistory(t);
  actions.act({ type: "custom", text: t });
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") { e.preventDefault(); submit(); }
}
</script>

<template>
  <div id="custom-input">
    <input id="free-text" ref="inputEl" v-model="text" list="custom-history" maxlength="60"
           placeholder="另行作为……（如：把丹药偷偷喂给灵猫）" autocomplete="off"
           :disabled="game.inputLocked" @keydown="onKeydown">
    <datalist id="custom-history">
      <option v-for="h in history" :key="h" :value="h"></option>
    </datalist>
    <button id="btn-custom" type="button" :disabled="game.inputLocked" @click="submit">行 事</button>
  </div>
</template>
