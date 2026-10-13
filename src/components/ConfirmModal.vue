<script setup lang="ts">
/* 重开确认弹窗：轮回档案提示 + 彻底清档（v3.13.2，二步确认）
   ——「再入轮回」留江湖记忆；「清空一切」把本设备全部本地数据归零，不可恢复 */
import { game, actions } from "../stores/game";
</script>

<template>
  <div id="confirm" :class="{ on: game.confirmOpen }">
    <div class="confirm-card">
      <template v-if="!game.confirmWipe">
        <h3>尘缘已了？</h3>
        <p id="confirm-text">{{ game.confirmText }}</p>
        <div class="row">
          <button type="button" class="cbtn" id="btn-cancel" @click="game.confirmOpen = false">回返</button>
          <button type="button" class="cbtn danger" id="btn-confirm-restart" @click="actions.confirmRestart()">再入轮回</button>
        </div>
        <div class="row wipe-row">
          <button type="button" class="cbtn ghost" id="btn-wipe-all"
                  title="抹去本设备上的全部记录：进度、名册、世数、历史与日志" @click="actions.requestWipe()">清空一切</button>
        </div>
      </template>
      <template v-else>
        <h3>此去无回</h3>
        <p id="confirm-wipe-text">将清空本设备上的全部记录：当前进度、轮回名册、世数、输入历史与对局日志，一并抹去，无法恢复。确定要重开天地么？</p>
        <div class="row">
          <button type="button" class="cbtn" id="btn-wipe-cancel" @click="actions.cancelWipe()">回返</button>
          <button type="button" class="cbtn danger solid" id="btn-wipe-confirm" @click="actions.wipeAll()">确认清空</button>
        </div>
      </template>
    </div>
  </div>
</template>
