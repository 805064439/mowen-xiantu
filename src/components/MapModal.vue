<script setup lang="ts">
/* 舆图（v3.13 · M1 + v3.13.1 · M2前半）：白名单地点水墨图。
   纯展示——当前位置高亮，点地点看「风土人情 + 出没妖兽 + 可访故人」。
   移动仍走叙事（AI 申报 + 代码白名单裁决），这里不给「瞬移」按钮，避免绕过耗时与风险。 */
import { computed, ref } from "vue";
import { game } from "../stores/game";
import { PLACES, placeOf } from "../game/constants";
import type { NpcEntry } from "../game/types";

const cur = computed(() => game.state?.location || "");
const curPlace = computed(() => placeOf(cur.value));

/* 当前选中查看的地点（默认 = 脚下） */
const selected = ref(cur.value || "qingniu_shan");
const selPlace = computed(() => placeOf(selected.value));

/* 此地的故人：名册里现居/常驻在此的相识人物 */
const residents = computed<NpcEntry[]>(() =>
  (game.state?.npcs || []).filter(n => n.location && n.location === selected.value),
);

function pick(key: string) { selected.value = key; }
function visit(n: NpcEntry) {
  game.mapOpen = false;        // 收起舆图，让详情卡独占
  game.npcDetail = n.name;
}

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
          :class="[kindTone(p.kind), { here: p.key === cur, sel: p.key === selected }]"
          :style="{ left: p.x + '%', top: p.y + '%' }"
          :title="`${p.name} · ${p.kind}`"
          @click.stop="pick(p.key)"
        >
          <span class="place-name">{{ p.name }}</span>
          <span class="place-kind">{{ p.kind }}</span>
        </button>
      </div>

      <!-- v3.13.1：点地点看风土人情 / 出没妖兽 / 可访故人 -->
      <div class="map-detail">
        <div class="md-head">
          <span class="md-name">{{ selPlace.name }}</span>
          <span class="md-kind" :class="kindTone(selPlace.kind)">{{ selPlace.kind }}</span>
        </div>
        <p class="md-desc">{{ selPlace.desc }}</p>
        <p class="md-flavor">{{ selPlace.flavor }}</p>

        <div class="md-sec">出 没</div>
        <div class="md-fauna">
          <span v-for="f in selPlace.fauna" :key="f" class="md-chip">{{ f }}</span>
        </div>

        <div class="md-sec">故 人</div>
        <div v-if="residents.length" class="md-residents">
          <button v-for="n in residents" :key="n.name" type="button" class="md-res" @click="visit(n)">
            <span class="md-res-name">{{ n.name }}</span>
            <span class="md-res-title">{{ n.title }}</span>
          </button>
        </div>
        <p v-else class="md-empty">此间暂无你相识之人。</p>
      </div>

      <div class="sc-actions">
        <button type="button" class="sc-btn sc-close-btn" @click="game.mapOpen = false">合 卷</button>
      </div>
      <p class="sc-warn">行止随缘，所到之处皆由缘法指引——舆图只示方位，不代步。</p>
    </div>
  </div>
</template>
