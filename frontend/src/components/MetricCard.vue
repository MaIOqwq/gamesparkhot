<template>
  <div class="relative glass-card p-5 sm:p-6 overflow-hidden">
    <!-- 装饰渐变光晕 -->
    <div class="absolute -top-20 -right-20 w-40 h-40 opacity-[0.08] rounded-full"
      :class="isSentiment ? 'bg-gradient-to-br from-yellow-400 via-purple-400 to-pink-400' : 'bg-gradient-to-br from-primary to-secondary'"
    />

    <div class="relative">
      <!-- 标题行 -->
      <div class="flex items-center gap-2.5 mb-4">
        <div class="w-1.5 h-5 rounded-full" :class="isSentiment ? 'bg-gradient-to-b from-yellow-400 to-purple-400' : 'bg-gradient-to-b from-primary to-secondary'" />
        <h3 class="text-sm font-medium text-slate-500 tracking-wide">{{ title }}</h3>
      </div>

      <!-- 值区域 -->
      <div v-if="!sentimentData" class="space-y-1">
        <div class="flex items-baseline gap-2">
          <span class="stat-value gradient-text">{{ typeof value === 'number' ? Math.floor(value).toLocaleString() : value }}</span>
          <span v-if="unit" class="text-sm text-slate-400">{{ unit }}</span>
        </div>
      </div>

      <!-- 迷你折线图 -->
      <div v-if="trendData && trendData.length > 0 && !sentimentData" class="mt-3 h-14">
        <div ref="chartRef" class="w-full h-full"></div>
      </div>

      <!-- 情感占比分布 -->
      <div v-if="sentimentData" class="space-y-3">
        <div class="flex items-center gap-3">
          <div class="flex-1">
            <div class="flex justify-between text-xs mb-1">
              <span class="text-green-600">正面</span>
              <span class="text-slate-500">{{ sentimentData.positive }}%</span>
            </div>
            <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full rounded-full bg-gradient-to-r from-green-500 to-green-400 transition-all duration-700 ease-out" :style="{ width: sentimentData.positive + '%' }" />
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="flex-1">
            <div class="flex justify-between text-xs mb-1">
              <span class="text-yellow-600">中性</span>
              <span class="text-slate-500">{{ sentimentData.neutral }}%</span>
            </div>
            <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full rounded-full bg-gradient-to-r from-yellow-500 to-yellow-400 transition-all duration-700 ease-out" :style="{ width: sentimentData.neutral + '%' }" />
            </div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="flex-1">
            <div class="flex justify-between text-xs mb-1">
              <span class="text-red-600">负面</span>
              <span class="text-slate-500">{{ sentimentData.negative }}%</span>
            </div>
            <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full rounded-full bg-gradient-to-r from-red-500 to-red-400 transition-all duration-700 ease-out" :style="{ width: sentimentData.negative + '%' }" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import * as echarts from 'echarts';

interface Props {
  title: string;
  value?: string | number;
  unit?: string;
  change?: number;
  changeDesc?: string;
  trendData?: number[];
  sentimentData?: {
    positive: number;
    neutral: number;
    negative: number;
  };
  mediaData?: {
    social: number;
    traditional: number;
  };
}

const props = defineProps<Props>();
const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;
let resizeFn: (() => void) | null = null;

const isSentiment = computed(() => !!props.sentimentData);

const initChart = () => {
  if (!chartRef.value || !props.trendData?.length) return;

  if (chart) chart.dispose();

  chart = echarts.init(chartRef.value, null, { renderer: 'canvas' });

  const option = {
    grid: { left: 0, right: 0, top: 2, bottom: 0 },
    xAxis: {
      type: 'category',
      data: props.trendData.map((_, i) => i),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
      min: (value: { min: number; max: number }) => Math.max(0, value.min - 10),
    },
    series: [{
      data: props.trendData,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: {
        color: '#3b82f6',
        width: 2
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(59, 130, 246, 0.25)' },
            { offset: 1, color: 'rgba(59, 130, 246, 0.02)' }
          ]
        }
      }
    }],
    animationDuration: 800,
    animationEasing: 'cubicOut' as const
  };

  chart.setOption(option);

  resizeFn = () => chart?.resize();
  window.addEventListener('resize', resizeFn);
};

watch(() => props.trendData, () => {
  if (props.trendData?.length) initChart();
  else if (chart) { chart.dispose(); chart = null; }
}, { immediate: true });

onUnmounted(() => {
  if (resizeFn) window.removeEventListener('resize', resizeFn);
  chart?.dispose();
});
</script>
