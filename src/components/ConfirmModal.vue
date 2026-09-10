<script setup lang="ts">
/* 重开确认弹窗：轮回档案提示 */
import { game, actions } from "../stores/game";
</script>

<template>
  <div id="confirm" :class="{ on: game.confirmOpen }">
    <div class="confirm-card">
      <h3>尘缘已了？</h3>
      <p id="confirm-text">{{ game.confirmText }}</p>
      <div class="row">
        <button type="button" class="cbtn" id="btn-cancel" @click="game.confirmOpen = false">回返</button>
        <button type="button" class="cbtn danger" id="btn-confirm-restart" @click="actions.confirmRestart()">再入轮回</button>
      </div>
    </div>
  </div>
</template>
