<script setup lang="ts">
/* 回到当下浮标：视口距页面底部超过 1.5 屏时浮现右下角，点击平滑滚到最新剧情 */
import { ref, onMounted, onBeforeUnmount } from "vue";

const visible = ref(false);

function onScroll() {
  const dist = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
  visible.value = dist > window.innerHeight;   // 距底超一屏即显示
}

function goBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

onMounted(() => { window.addEventListener("scroll", onScroll, { passive: true }); onScroll(); });
onBeforeUnmount(() => window.removeEventListener("scroll", onScroll));
</script>

<template>
  <button id="back-now" type="button" :class="{ on: visible }" aria-label="回到最新剧情" @click="goBottom">▾</button>
</template>
