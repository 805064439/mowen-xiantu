<script setup lang="ts">
/* 突破特效：白光闪 + 境界大字（2 秒） */
import { game } from "../stores/game";
</script>

<template>
  <div v-if="game.btFlash" id="bt-flash">
    <div class="bt-word">{{ game.btFlash }}！</div>
    <div class="bt-sub">境 界 精 进</div>
  </div>
</template>
