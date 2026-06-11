<template>
  <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="px-5 py-4 border-b border-slate-100">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
          <h3 class="text-sm font-semibold text-slate-800">运营预警</h3>
        </div>
        <span class="text-xs text-slate-400 bg-slate-50 px-2.5 py-1 rounded-full">
          {{ filteredWarnings.length }} 个预警
        </span>
      </div>
    </div>

    <!-- 筛选 -->
    <div class="px-5 py-2.5 border-b border-slate-50 flex gap-2">
      <button
        v-for="f in filters"
        :key="f.value"
        @click="activeFilter = f.value"
        class="text-xs px-2.5 py-1 rounded-full transition-all"
        :class="activeFilter === f.value
          ? 'bg-slate-800 text-white'
          : 'bg-slate-100 text-slate-500 hover:bg-slate-200'"
      >{{ f.label }}</button>
    </div>

    <!-- 预警列表 -->
    <div class="divide-y divide-slate-50 max-h-96 overflow-y-auto">
        <div
          v-for="(w, i) in filteredWarnings"
          :key="w.keyword"
          @click="onToggleExpand(i)"
          class="px-5 py-3 hover:bg-slate-50/50 cursor-pointer transition-colors"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="flex items-center gap-3 min-w-0 flex-1">
              <span class="w-2 h-2 rounded-full flex-shrink-0" :class="levelClass(w.level)"></span>
              <span class="text-sm font-medium text-slate-700 truncate">{{ w.keyword }}</span>
              <span class="text-xs px-1.5 py-0.5 rounded font-medium flex-shrink-0" :class="trendBadgeClass(w.trendCode)">{{ w.trend }}</span>
            </div>
            <div class="flex items-center gap-4 flex-shrink-0">
              <div class="text-right">
                <div class="text-xs text-slate-400">热度</div>
                <div class="text-sm font-semibold text-slate-700">{{ w.currentHot.toFixed(2) }}</div>
              </div>
              <div class="text-right min-w-[4rem]">
                <div class="text-xs text-slate-400">变化</div>
                <div class="text-sm font-semibold" :class="w.changeRate > 0 ? 'text-red-500' : w.changeRate < 0 ? 'text-green-500' : 'text-slate-400'">{{ (w.changeRate * 100).toFixed(0) }}%</div>
              </div>
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-slate-300 transition-transform" :class="expandedIndex === i ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
          <div v-if="expandedIndex === i" class="mt-2.5 ml-5 pl-2 border-l-2 border-slate-100">
            <div v-if="detailLoading.has(i)" class="text-xs text-slate-400 py-1">加载中...</div>
            <div v-else class="space-y-1.5 text-xs text-slate-500">
              <div v-if="detailData.get(i)?.topContent" class="flex items-start gap-2">
                <span class="text-slate-400 whitespace-nowrap mt-0.5">热门:</span>
                <div class="min-w-0">
                  <span class="text-slate-700 truncate block">{{ detailData.get(i)?.topContent?.title }}</span>
                  <span class="text-slate-400 text-[11px]">{{ detailData.get(i)?.topContent?.platform }}</span>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-slate-400">趋势:</span>
                <span class="font-medium" :class="w.changeRate > 0 ? 'text-red-500' : w.changeRate < 0 ? 'text-green-500' : 'text-slate-400'">{{ w.trend }}</span>
                <span class="text-slate-300">·</span>
                <span :class="w.changeRate > 0 ? 'text-red-500' : w.changeRate < 0 ? 'text-green-500' : 'text-slate-400'">{{ (w.changeRate * 100).toFixed(0) }}%</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-slate-400">情绪:</span>
                <span class="text-green-600">正 {{ sentPct(detailData.get(i)?.sentiment?.positive).toFixed(0) }}%</span>
                <span class="text-yellow-500">中 {{ sentPct(detailData.get(i)?.sentiment?.neutral).toFixed(0) }}%</span>
                <span class="text-red-500">负 {{ sentPct(detailData.get(i)?.sentiment?.negative).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="filteredWarnings.length === 0" class="px-5 py-8 text-center text-sm text-slate-400">暂无预警</div>
      </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { WarningDTO } from '../types';
import { getTrendData, getMetrics } from '../api';

const props = defineProps<{ warnings: WarningDTO[] }>();

const activeFilter = ref('all');
const expandedIndex = ref(-1);
const detailData = ref<Map<number, any>>(new Map());
const detailLoading = ref<Set<number>>(new Set());

const filters = [
  { label: '全部', value: 'all' },
  { label: '增长', value: '增长' },
  { label: '下降', value: '下降' },
  { label: '平稳', value: '平稳' },
];

const filteredWarnings = computed(() => {
  if (activeFilter.value === 'all') return props.warnings;
  return props.warnings.filter(w => w.trend === activeFilter.value);
});

// ---------- 工具函数 ----------
const sentPct = (v: any) => typeof v === 'number' ? v : 0;

const onToggleExpand = async (i: number) => {
  if (expandedIndex.value === i) { expandedIndex.value = -1; return; }
  expandedIndex.value = i;
  if (detailData.value.has(i)) return;

  const w = filteredWarnings.value[i];
  detailLoading.value.add(i);
  try {
    const [trendRes, metricsRes] = await Promise.all([
      getTrendData(w.keyword),
      getMetrics(w.keyword),
    ]);

    let topContent = null;
    if (trendRes.code === 200 && trendRes.data?.length) {
      for (const item of [...trendRes.data].reverse()) {
        if (item.topContents?.length) { topContent = item.topContents[0]; break; }
      }
    }

    let sentiment = { positive: 0, neutral: 0, negative: 0 };
    if (metricsRes.code === 200 && metricsRes.data?.sentimentRatio) {
      sentiment = metricsRes.data.sentimentRatio;
    }

    detailData.value.set(i, { topContent, sentiment });
  } catch (e) {
    console.error('加载详情失败', e);
  } finally {
    detailLoading.value.delete(i);
  }
};

const levelClass = (level: string) => {
  switch (level) {
    case 'danger': return 'bg-red-500';
    case 'warning': return 'bg-amber-400';
    default: return 'bg-slate-300';
  }
};

const trendBadgeClass = (code: number) => {
  switch (code) {
    case 4: return 'bg-red-50 text-red-600';
    case 3: return 'bg-orange-50 text-orange-600';
    case 2: return 'bg-slate-50 text-slate-500';
    case 1: return 'bg-blue-50 text-blue-600';
    case 0: return 'bg-green-50 text-green-600';
    default: return 'bg-slate-50 text-slate-500';
  }
};

</script>
