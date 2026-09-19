<script setup lang="ts">
/* 对局日志：把每一轮的剧情与选项导出（JSONL 供脚本、Markdown 供人读）。
   数据来自独立的 localStorage 日志键，不进存档也不进仙缘令。 */
import { ref, computed, onMounted } from "vue";
import { game, actions } from "../stores/game";
import { loadJournal, toText, JOURNAL_MAX } from "../game/journal";

const busy = ref<"" | "jsonl" | "md" | "txt" | "copy">("");
const msg = ref("");

const entries = ref(loadJournal());
const count = computed(() => entries.value.length);
const bytes = computed(() => {
  try { return JSON.stringify(entries.value).length; } catch (e) { return 0; }
});
const kb = computed(() => (bytes.value / 1024).toFixed(1) + " KB");
const preview = computed(() => {
  const tail = entries.value.slice(-3);
  return tail.length ? toText(tail) : "（尚未开启日志——行动一轮后即有记录）";
});
const full = computed(() => count.value >= JOURNAL_MAX);

onMounted(() => { entries.value = loadJournal(); });

function refresh() { entries.value = loadJournal(); }

function download(fmt: "jsonl" | "md" | "txt") {
  if (busy.value || !count.value) return;
  busy.value = fmt;
  msg.value = "";
  try {
    const out = actions.journalExport(fmt);
    if (!out) { msg.value = "日志为空。"; return; }
    const url = URL.createObjectURL(new Blob([out.content], { type: out.mime + ";charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = out.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    msg.value = "已导出 " + out.filename;
  } catch (e) {
    msg.value = "导出失败：浏览器可能不支持下载，请改用「复制全文」。";
  } finally {
    busy.value = "";
  }
}

async function copyAll() {
  if (busy.value || !count.value) return;
  busy.value = "copy";
  msg.value = "";
  const out = actions.journalExport("md");
  if (!out) { msg.value = "日志为空。"; busy.value = ""; return; }
  let ok = false;
  try { await navigator.clipboard.writeText(out.content); ok = true; } catch (e) { ok = false; }
  if (!ok) {
    const ta = document.querySelector<HTMLTextAreaElement>(".jr-preview");
    ta?.focus();
    ta?.select();
  }
  msg.value = ok ? "Markdown 全文已复制" : "已选中全文，请手动复制";
  busy.value = "";
  setTimeout(() => { if (msg.value.indexOf("复制") >= 0) msg.value = ""; }, 2200);
}

function doClear() {
  if (!count.value) return;
  actions.journalClear();
  refresh();
  msg.value = "日志已清空（存档不受影响）";
}

function close() { game.journalOpen = false; }
</script>

<template>
  <div id="journal" @click="close">
    <div class="sc-card jr-card" @click.stop>
      <h3>对 局 日 志</h3>
      <p class="sc-hint">每轮剧情与选项，留作排查与离线回溯之用。</p>

      <p class="jr-stat">
        共 <b>{{ count }}</b> 轮 · {{ kb }}
        <span v-if="full">（已满，只留最近 {{ JOURNAL_MAX }} 轮）</span>
      </p>

      <textarea class="sc-out jr-preview" readonly :value="preview"
                @focus="($event.target as HTMLTextAreaElement).select()"></textarea>

      <div class="sc-actions jr-grid">
        <button type="button" class="sc-btn" :disabled="!count || !!busy" @click="download('md')">
          {{ busy === "md" ? "导出中…" : "导出 Markdown" }}</button>
        <button type="button" class="sc-btn" :disabled="!count || !!busy" @click="download('jsonl')">
          {{ busy === "jsonl" ? "导出中…" : "导出 JSONL" }}</button>
        <button type="button" class="sc-btn" :disabled="!count || !!busy" @click="download('txt')">
          {{ busy === "txt" ? "导出中…" : "导出 TXT" }}</button>
        <button type="button" class="sc-btn" :disabled="!count || !!busy" @click="copyAll">
          {{ busy === "copy" ? "处理中…" : "复制全文" }}</button>
      </div>

      <div class="sc-actions">
        <button type="button" class="sc-btn jr-clear" :disabled="!count" @click="doClear">清空日志</button>
        <button type="button" class="sc-btn sc-close-btn" @click="close">合起</button>
      </div>

      <p class="sc-warn" v-if="!msg">日志只存在本机，导出才会离开此设备。</p>
      <p class="jr-msg" v-else>{{ msg }}</p>
    </div>
  </div>
</template>
