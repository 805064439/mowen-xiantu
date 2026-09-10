<script setup lang="ts">
/* 叙事区：段落流 + 加载提示。点击文字跳过打字机。 */
import { game, actions } from "../stores/game";
</script>

<template>
  <div id="story-card">
    <div id="story" @click="actions.skipTyper()">
      <p v-for="para in game.scenes" :key="para.id" class="scene">{{ para.text }}</p>
    </div>
    <div id="loading" :class="{ on: game.loading }">天机推演中<i>·</i><i>·</i><i>·</i></div>
  </div>
</template>
