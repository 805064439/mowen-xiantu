<script setup lang="ts">
/* 布局根组件：头部（境界/灵根/徽章）+ 各功能区组合 */
import { onMounted, computed } from "vue";
import { game, actions, metaText } from "./stores/game";
import { REALMS, EXP_MAX, VERSION } from "./game/constants";
import StatusPanel from "./components/StatusPanel.vue";
import StoryView from "./components/StoryView.vue";
import ChoiceList from "./components/ChoiceList.vue";
import FreeInput from "./components/FreeInput.vue";
import FloatLayer from "./components/FloatLayer.vue";
import BtFlash from "./components/BtFlash.vue";
import EndingMask from "./components/EndingMask.vue";
import ConfirmModal from "./components/ConfirmModal.vue";
import StickyBar from "./components/StickyBar.vue";
import StatusDrawer from "./components/StatusDrawer.vue";
import BackToNow from "./components/BackToNow.vue";
import SaveCodeModal from "./components/SaveCodeModal.vue";
import JournalModal from "./components/JournalModal.vue";
import ShopModal from "./components/ShopModal.vue";
import ItemDetail from "./components/ItemDetail.vue";

const realm = computed(() => REALMS[game.state?.realm_index ?? 0]);
const isHeavenRoot = computed(() => (game.state?.spirit_root || "").startsWith("天灵根"));
const realmFull = computed(() => {
  const lv = game.state?.realm_index ?? 0;
  if (lv < 9 && (game.state?.exp ?? 0) >= EXP_MAX[lv]) return "圆满 · 可冲关";
  return lv === 9 ? "第一章 · 已筑基" : "";
});

onMounted(() => { actions.init(); });
</script>

<template>
  <div id="app-root">
    <header>
      <div class="seal"><span>墨</span><span>问</span><span>仙</span><span>途</span></div>
      <div class="title-wrap">
        <h1>墨 问 仙 途</h1>
        <div class="realm-line">
          <span id="realm">{{ realm }}</span>
          <span id="root-badge" :class="{ 'root-heaven': isHeavenRoot }"
                :title="game.state?.spirit_root ? '灵根资质：影响修炼速度与冲关成败' : ''">
            {{ game.state?.spirit_root || "" }}
          </span>
          <span id="realm-full">{{ realmFull }}</span>
        </div>
      </div>
      <span id="mode-badge" v-show="game.mockMode" title="未配置 DeepSeek API Key，当前为本地演武剧情">演武模式</span>
    </header>

    <StatusPanel />
    <StoryView />
    <ChoiceList />
    <FreeInput />

    <footer>
      <span id="meta">{{ metaText }}</span>
      <span>点击剧情文字可跳过打字</span>
      <span class="foot-btns">
        <span id="ver" :title="game.buildInfo || '版本号：当前构建的代码版本'">v{{ VERSION }}</span>
        <button id="btn-shop" type="button" @click="game.shopOpen = true">坊市</button>
        <button id="btn-journal" type="button" @click="game.journalOpen = true">对局日志</button>
        <button id="btn-savecode" type="button" @click="game.saveCodeOpen = true">仙缘令</button>
        <button id="btn-restart" type="button" @click="actions.requestRestart()">再入轮回</button>
      </span>
    </footer>
  </div>

  <FloatLayer />
  <BtFlash />
  <EndingMask />
  <ConfirmModal />
  <StickyBar />
  <StatusDrawer />
  <BackToNow />
  <SaveCodeModal v-if="game.saveCodeOpen" />
  <JournalModal v-if="game.journalOpen" />
  <ShopModal v-if="game.shopOpen" />
  <ItemDetail v-if="game.itemDetail" />
</template>
