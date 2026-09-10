<script setup lang="ts">
/* 飘字层：数值/物品增减的浮动反馈 */
import { game } from "../stores/game";
</script>

<template>
  <div id="floats">
    <span v-for="f in game.floats" :key="f.id" class="float" :class="f.cls">{{ f.text }}</span>
  </div>
</template>
