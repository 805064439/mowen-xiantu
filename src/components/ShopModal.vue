<script setup lang="ts">
/* 坊市：固定价格买卖（经济锚点，纯后端裁决不掷骰）。买入按表，卖出五折。 */
import { computed } from "vue";
import { game, actions } from "../stores/game";

const SHOP_PRICES: { name: string; price: number }[] = [
  { name: "凝气丹", price: 40 },
  { name: "回气丹", price: 25 },
  { name: "疗伤丹", price: 15 },
  { name: "清心丹", price: 20 },
  { name: "辟谷丹", price: 10 },
];
const SELL_RATIO = 0.5;
const SELL_FALLBACK = 5; // 不在收购名单的杂物单件卖价

const stones = computed(() => game.state?.spirit_stones ?? 0);
const sellables = computed(() => (game.state?.items ?? [])
  .map(it => ({ ...it, sell: Math.floor((SHOP_PRICES.find(p => p.name === it.name)?.price ?? 10) * SELL_RATIO) }))
  .filter(it => it.qty > 0));

function buy(name: string) {
  if (game.loading) return;
  actions.shopAct({ type: "shop_buy", name, qty: 1 });
}
function sell(name: string) {
  if (game.loading) return;
  actions.shopAct({ type: "shop_sell", name, qty: 1 });
}
</script>

<template>
  <div id="shop" @click="game.shopOpen = false">
    <div class="sc-card shop-card" @click.stop>
      <h3>青 牛 镇 坊 市</h3>
      <p class="sc-hint">童叟无欺，价有定数。身怀灵石 <b>{{ stones }}</b> 枚。</p>

      <div class="shop-sec-title">购 药</div>
      <ul class="shop-list">
        <li v-for="p in SHOP_PRICES" :key="p.name">
          <span class="shop-item-name">{{ p.name }}</span>
          <span class="shop-price">{{ p.price }} 灵石</span>
          <button type="button" class="sc-btn shop-op" :disabled="game.loading || stones < p.price"
                  @click="buy(p.name)">买</button>
        </li>
      </ul>

      <div class="sc-divider"><span>出 售 行 囊 之 物</span></div>
      <ul class="shop-list" v-if="sellables.length">
        <li v-for="it in sellables" :key="it.name">
          <span class="shop-item-name">{{ it.name }}<small> ×{{ it.qty }}</small></span>
          <span class="shop-price">{{ it.sell }} 灵石</span>
          <button type="button" class="sc-btn shop-op sell" :disabled="game.loading"
                  @click="sell(it.name)">卖</button>
        </li>
      </ul>
      <p class="sc-hint" v-else>行囊空空，无物可售。</p>

      <div class="sc-actions">
        <button type="button" class="sc-btn sc-close-btn" @click="game.shopOpen = false">离市</button>
      </div>
      <p class="sc-warn">出售价为购入五折；杂物无人问津，仅按 {{ SELL_FALLBACK }} 灵石收。</p>
    </div>
  </div>
</template>
