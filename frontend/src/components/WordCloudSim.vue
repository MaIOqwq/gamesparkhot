<template>
  <div class="relative glass-card p-5 sm:p-6">
    <div class="absolute -bottom-16 -right-16 w-32 h-32 bg-gradient-to-tl from-purple-500/5 to-transparent rounded-full" />

    <div class="relative">
      <div class="flex items-center gap-2.5 mb-1">
        <div class="w-1.5 h-5 rounded-full bg-gradient-to-b from-purple-500 to-pink-500" />
        <h3 class="text-sm font-medium text-slate-500 tracking-wide">热点词云</h3>
      </div>
      <div class="glow-line mb-5" />

      <div v-if="loading" class="h-80 flex items-center justify-center">
        <div class="flex flex-col items-center gap-3">
          <div class="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          <span class="text-xs text-slate-400">加载中...</span>
        </div>
      </div>

      <div v-if="!loading && hasData" ref="chartRef" class="h-80" />

      <div v-if="!loading && !hasData" class="h-80 flex items-center justify-center">
        <div class="text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-slate-200 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
          </svg>
          <p class="text-sm text-slate-400">暂无热词数据</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, watch, onUnmounted } from 'vue';
import * as echarts from 'echarts';
import 'echarts-wordcloud';
import { getWordsData } from '../api';
import type { WordDTO } from '../types';

const props = defineProps<{
  currentKeyword: string
  timeRange: string
}>();

const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;
let resizeFn: (() => void) | null = null;
const loading = ref(true);
const hasData = ref(false);
const words = ref<WordDTO[]>([]);

const COLORS = [
  '#3b82f6', '#06b6d4', '#8b5cf6', '#22c55e',
  '#eab308', '#f97316', '#ef4444', '#ec4899',
  '#14b8a6', '#6366f1'
];

const loadData = async () => {
  try {
    const response = await getWordsData(props.currentKeyword, props.timeRange);
    words.value = response.data || [];
    hasData.value = words.value.length > 0;
  } catch (error) {
    console.error('加载热词数据失败:', error);
  }
};

const renderChart = async () => {
  loading.value = false;
  await nextTick();
  if (chartRef.value && hasData.value) {
    initChart(words.value);
  }
};

onMounted(async () => {
  await loadData();
  await renderChart();
});

watch(() => [props.currentKeyword, props.timeRange], async () => {
  loading.value = true;
  await loadData();
  await renderChart();
});

const initChart = (words: WordDTO[]) => {
  if (!chartRef.value) return;
  if (chart) chart.dispose();

  chart = echarts.init(chartRef.value);

  const option = {
    tooltip: {
      show: true,
      backgroundColor: '#ffffff',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      textStyle: { color: '#1e293b', fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width:260px;',
      formatter: (params: any) => {
        const wd = words.find(w => w.word === params.name);
        let html = `<div style="font-weight:600;color:#1e293b;margin-bottom:4px;">${params.name}</div>`;
        html += `<div style="color:#64748b;font-size:11px;">权重 ${params.value}</div>`;
        if (wd?.hotTitle) {
          html += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid #f1f5f9;">
            <div style="color:#94a3b8;font-size:10px;">最高热度内容</div>
            <div style="color:#334155;font-size:11px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${wd.hotTitle}</div>
            <div style="display:flex;gap:8px;margin-top:2px;font-size:10px;">
              <span style="color:#3b82f6;">${wd.hotPlatform}</span>
              <span style="color:#f59e0b;font-weight:600;">${wd.hotValue}</span>
            </div>
          </div>`;
        }
        return html;
      }
    },
    series: [{
      type: 'wordCloud',
      shape: 'circle' as const,
      left: 'center',
      top: 'center',
      width: '95%',
      height: '95%',
      sizeRange: [12, 48],
      rotationRange: [-30, 30],
      rotationStep: 15,
      gridSize: 6,
      drawOutOfBound: false,
      textStyle: {
        fontFamily: 'Inter, sans-serif',
        fontWeight: 'bold' as const,
        color: (echartsWord: any) => {
          const idx = words.findIndex(w => w.word === echartsWord.name);
          return COLORS[idx % COLORS.length];
        }
      },
      emphasis: {
        textStyle: {
          shadowBlur: 15,
          shadowColor: 'rgba(59, 130, 246, 0.3)'
        }
      },
      data: words.map(item => ({
        name: item.word,
        value: item.weight,
      })),
      animationDuration: 1200,
      animationEasing: 'cubicOut' as const,
    }]
  };

  chart.setOption(option);

  resizeFn = () => chart?.resize();
  window.addEventListener('resize', resizeFn);
};

onUnmounted(() => {
  if (resizeFn) window.removeEventListener('resize', resizeFn);
  chart?.dispose();
});
</script>
