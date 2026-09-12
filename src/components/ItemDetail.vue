<script setup lang="ts">
/* 道具详情：点行囊之物先看到「这是什么、吃了会怎样」，再决定服不服。
   旧版是点一下直接服用 —— 玩家在没有说明书的情况下被消耗掉道具，
   材料类点了还会白扣一轮。这里把「知情」和「执行」拆成两步。 */
import { computed } from "vue";
import { game, actions } from "../stores/game";
import { itemInfo, canUseItem } from "../game/constants";

const name = computed(() => game.itemDetail || "");
const info = computed(() => itemInfo(name.value));
const qty = computed(() => {
  const it = (game.state?.items ?? []).find((i) => i.name === name.value);
  return it?.qty ?? 0;
});
const rarity = computed(() => {
  const it = (game.state?.items ?? []).find((i) => i.name === name.value);
  return it?.rarity || "";
});
const usable = computed(() => canUseItem(name.value) && qty.value > 0);

const kindLabel: Record<string, string> = {
  pill: "丹 药", material: "材 料", gear: "兵 刃",
};

function close() { game.itemDetail = null; }

function useIt() {
  if (!usable.value || game.loading) return;
  const n = name.value;
  close();
  actions.act({ type: "use_item", name: n });
}
</script>

<template>
  <div id="item-detail" @click="close">
    <div class="sc-card id-card" @click.stop>
      <div class="id-kind">{{ kindLabel[info.kind] || "杂 物" }}</div>
      <h3>{{ name }}</h3>
      <div class="id-meta">
        <span v-if="rarity" class="id-rarity">{{ rarity }}</span>
        <span class="id-qty">囊中 {{ qty }} 份</span>
      </div>

      <div class="id-effect">{{ info.effect }}</div>
      <p class="id-desc">{{ info.desc }}</p>
      <p class="id-hint" v-if="info.hint">{{ info.hint }}</p>
      <p class="id-hint warn" v-else-if="info.kind !== 'pill'">
        此物不可服用，留着自有他用。
      </p>

      <div class="sc-actions id-actions">
        <button type="button" class="sc-btn sc-close-btn" @click="close">收起</button>
        <button type="button" class="sc-btn id-use" :disabled="!usable || game.loading"
                :title="usable ? '服用一份' : (qty ? '此物不可服用' : '行囊中已无此物')"
                @click="useIt">
          {{ game.loading ? "服用中…" : "服用" }}
        </button>
      </div>
    </div>
  </div>
</template>
