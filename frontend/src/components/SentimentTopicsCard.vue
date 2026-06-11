<template>
  <div class="glass-card p-5 sm:p-6">
    <div class="flex items-center gap-2.5 mb-1">
      <div class="w-1.5 h-5 rounded-full bg-gradient-to-b from-emerald-500 to-teal-500" />
      <h3 class="text-sm font-medium text-slate-500 tracking-wide">情绪焦点</h3>
    </div>
    <div class="glow-line mb-5" />

    <div v-if="loading" class="h-48 flex items-center justify-center">
      <div class="flex flex-col items-center gap-3">
        <div class="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
        <span class="text-xs text-slate-400">加载情绪分析中...</span>
      </div>
    </div>

    <div v-else-if="!hasData" class="h-48 flex items-center justify-center">
      <div class="text-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-slate-200 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p class="text-sm text-slate-400">暂无情绪数据</p>
      </div>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <!-- 正面 -->
      <div class="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span class="text-xs font-semibold text-emerald-700">正面</span>
          <span class="text-xs text-emerald-400 ml-auto">{{ count('positive') }} 个词</span>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="w in groups['positive']?.words || []"
            :key="w.word"
            class="inline-block rounded-full bg-white/80 border border-emerald-200 text-emerald-700 cursor-default transition-all hover:bg-emerald-100"
            :style="wordStyle(w.weight)"
          >{{ w.word }}</span>
        </div>
        <div v-if="!groups['positive']?.words?.length" class="text-xs text-slate-400 py-4 text-center">暂无数据</div>
      </div>

      <!-- 中性 -->
      <div class="rounded-xl border border-slate-200 bg-slate-50/40 p-4">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-2.5 h-2.5 rounded-full bg-slate-400" />
          <span class="text-xs font-semibold text-slate-600">中性</span>
          <span class="text-xs text-slate-400 ml-auto">{{ count('neutral') }} 个词</span>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="w in groups['neutral']?.words || []"
            :key="w.word"
            class="inline-block rounded-full bg-white/80 border border-slate-200 text-slate-600 cursor-default transition-all hover:bg-slate-100"
            :style="wordStyle(w.weight)"
          >{{ w.word }}</span>
        </div>
        <div v-if="!groups['neutral']?.words?.length" class="text-xs text-slate-400 py-4 text-center">暂无数据</div>
      </div>

      <!-- 负面 -->
      <div class="rounded-xl border border-red-200 bg-red-50/40 p-4">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-2.5 h-2.5 rounded-full bg-red-500" />
          <span class="text-xs font-semibold text-red-600">负面</span>
          <span class="text-xs text-red-400 ml-auto">{{ count('negative') }} 个词</span>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="w in groups['negative']?.words || []"
            :key="w.word"
            class="inline-block rounded-full bg-white/80 border border-red-200 text-red-600 cursor-default transition-all hover:bg-red-100"
            :style="wordStyle(w.weight)"
          >{{ w.word }}</span>
        </div>
        <div v-if="!groups['negative']?.words?.length" class="text-xs text-slate-400 py-4 text-center">暂无数据</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue';
import { getSentimentWords } from '../api';
import type { SentimentWordGroupDTO } from '../types';

const props = defineProps<{
  currentKeyword: string;
  timeRange: string;
}>();

const loading = ref(false);
const groups = reactive<Record<string, SentimentWordGroupDTO>>({});
const hasData = ref(false);

const count = (key: string) => groups[key]?.words?.length || 0;

const wordStyle = (weight: number) => {
  // weight 0-100, map to font-size 11-14px and padding
  const ratio = weight / 100;
  const size = 11 + ratio * 4;
  const px = 6 + ratio * 6;
  const py = 2 + ratio * 3;
  return {
    fontSize: `${size}px`,
    padding: `${py}px ${px}px`,
  };
};

const fetchData = async () => {
  loading.value = true;
  try {
    const res = await getSentimentWords(props.currentKeyword, props.timeRange);
    if (res.code === 200 && res.data) {
      Object.assign(groups, res.data);
      hasData.value = !!(groups['positive']?.words?.length || groups['neutral']?.words?.length || groups['negative']?.words?.length);
    }
  } catch (e) {
    console.error('获取情绪焦点词失败:', e);
  } finally {
    loading.value = false;
  }
};

watch(() => [props.currentKeyword, props.timeRange], fetchData, { immediate: true });
</script>
