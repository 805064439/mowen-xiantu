<script setup lang="ts">
/* 舆图（v3.13 · M1）：白名单地点水墨图。
   纯展示——当前位置高亮，点地点看简介。移动仍走叙事（AI 申报 + 代码白名单裁决），
   这里不给「瞬移」按钮，避免绕过耗时与风险。 */
import { computed } from "vue";
import { game } from "../stores/game";
import { PLACES, placeOf } from "../game/constants";

const cur = computed(() => game.state?.location || "");
const curPlace = computed(() => placeOf(cur.value));

function kindTone(kind: string): string {
  switch (kind) {
    case "险地": return "place-danger";
    case "秘境": return "place-secret";
    case "大城": return "place-city";
    case "渡口": return "place-port";
    default: return "";
  }
}
</script>

<template>
  <div id="map" @click="game.mapOpen = false">
    <div class="sc-card map-card" @click.stop>
      <h3>山 河 舆 图</h3>
      <p class="sc-hint">脚下<span class="map-cur-inline"> {{ curPlace.name }}</span> ·
        {{ curPlace.desc }}</p>

      <div class="map-sheet">
        <!-- 水墨背景：几笔淡山 + 一条官道 + 大泽（纯装饰） -->
        <svg class="map-bg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d="M8 70 Q22 52 34 66 T58 60 T88 52" class="map-ridge" />
          <path d="M14 84 Q34 78 52 84 T88 78" class="map-ridge map-ridge2" />
          <path d="M40 4 Q44 12 42 20 T46 40 T50 64" class="map-river" />
          <path d="M6 30 Q20 24 30 30 T52 26 T80 30" class="map-river map-river2" />
          <path d="M50 96 Q50 80 52 60 Q56 34 60 22" class="map-road" />
        </svg>

        <button
          v-for="p in PLACES"
          :key="p.key"
          type="button"
          class="place-dot"
          :class="[kindTone(p.kind), { here: p.key === cur }]"
          :style="{ left: p.x + '%', top: p.y + '%' }"
          :title="`${p.name} · ${p.kind}\n${p.desc}`"
          @click.stop=""
        >
          <span class="place-name">{{ p.name }}</span>
          <span class="place-kind">{{ p.kind }}</span>
        </button>
      </div>

      <ul class="map-legend">
        <li v-for="p in PLACES" :key="p.key" :class="{ here: p.key === cur }">
          <span class="lg-name">{{ p.name }}</span>
          <span class="lg-kind" :class="kindTone(p.kind)">{{ p.kind }}</span>
          <span class="lg-desc">{{ p.desc }}</span>
        </li>
      </ul>

      <div class="sc-actions">
        <button type="button" class="sc-btn sc-close-btn" @click="game.mapOpen = false">合 卷</button>
      </div>
      <p class="sc-warn">行止随缘，所到之处皆由缘法指引——舆图只示方位，不代步。</p>
    </div>
  </div>
</template>
