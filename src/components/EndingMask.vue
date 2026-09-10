<script setup lang="ts">
/* 第一章结局印章 */
import { game } from "../stores/game";
function close() { game.endingShown = false; }
</script>

<template>
  <div v-if="game.endingShown" id="ending-mask" @click="close">
    <div class="seal-end">
      <span>第一章</span>
      <small>· 完 ·</small>
    </div>
  </div>
</template>
