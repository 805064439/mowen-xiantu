<script setup lang="ts">
/* 仙缘令：导出/导入存档文本码。导出走当前进行中的进度，导入校验后覆盖本地档。 */
import { ref, onMounted } from "vue";
import { game, actions } from "../stores/game";

const code = ref("");
const input = ref("");
const copied = ref(false);
const importMsg = ref("");
const importing = ref(false);

onMounted(async () => {
  try { code.value = await actions.exportSaveCode(); }
  catch (e) { code.value = ""; }
});

async function copy() {
  if (!code.value) return;
  let ok = false;
  try { await navigator.clipboard.writeText(code.value); ok = true; } catch (e) { ok = false; }
  if (!ok) {
    // 剪贴板权限不可用时退化为全选，让用户手动长按复制
    const ta = document.querySelector<HTMLTextAreaElement>(".sc-out");
    ta?.focus();
    ta?.select();
  }
  copied.value = true;
  setTimeout(() => { copied.value = false; }, 1600);
}

async function doImport() {
  if (!input.value.trim() || importing.value) return;
  importing.value = true;
  importMsg.value = "";
  try {
    const ok = await actions.importSaveCode(input.value);
    if (!ok) importMsg.value = "此令无法辨识——请确认仙缘令文本完整无缺。";
  } catch (e) {
    importMsg.value = "此令无法辨识——请确认仙缘令文本完整无缺。";
  } finally {
    importing.value = false;
  }
}
</script>

<template>
  <div id="savecode" @click="game.saveCodeOpen = false">
    <div class="sc-card" @click.stop>
      <h3>仙 缘 令</h3>
      <p class="sc-hint">此令承载今生修行。复制留存，可于任何设备续缘。</p>

      <textarea class="sc-out" readonly :value="code"
                @focus="($event.target as HTMLTextAreaElement).select()"></textarea>
      <div class="sc-actions">
        <button type="button" class="sc-btn" :disabled="!code" @click="copy">{{ copied ? "✓ 已复制" : "复制仙缘令" }}</button>
        <button type="button" class="sc-btn sc-close-btn" @click="game.saveCodeOpen = false">合起</button>
      </div>

      <div class="sc-divider"><span>或 以 令 续 缘</span></div>

      <textarea class="sc-in" v-model="input" placeholder="粘贴仙缘令文本……" inputmode="text"></textarea>
      <div class="sc-actions">
        <button type="button" class="sc-btn sc-import" :disabled="!input.trim() || importing" @click="doImport">
          {{ importing ? "验令中……" : "导入并覆盖当前进度" }}</button>
      </div>
      <p class="sc-warn" v-if="!importMsg">导入将覆盖此设备上的当前进度，轮回名册不受影响。</p>
      <p class="sc-err" v-else>{{ importMsg }}</p>
    </div>
  </div>
</template>
