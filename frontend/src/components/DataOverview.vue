<template>
  <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <!-- 今日数据计数 -->
    <div class="px-5 py-4 border-b border-slate-100">
      <div class="flex items-center gap-1.5 mb-3">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        <span class="text-xs font-medium text-emerald-700">今日 {{ dataCount?.todayCount ?? 0 }} 条</span>
      </div>
      <!-- 2小时窗口曲线图 -->
      <div ref="hourlyChartRef" class="h-28" />
    </div>

    <!-- 最新数据 -->
    <div v-if="dataCount?.latestEntries?.length" class="px-5 py-3">
      <div class="flex items-center gap-2 mb-2">
        <div class="w-1 h-4 rounded-full bg-gradient-to-b from-primary to-secondary" />
        <h4 class="text-xs font-medium text-slate-500">最新数据</h4>
      </div>
      <div class="space-y-2">
        <div
          v-for="(entry, ei) in dataCount.latestEntries.slice(0, 5)"
          :key="ei"
          class="text-xs"
        >
          <div class="flex items-center gap-2">
            <span
              class="w-4 h-4 flex items-center justify-center rounded-full text-[10px] font-medium flex-shrink-0"
              :class="entry.platform === 'B站' ? 'bg-blue-50 text-blue-600' : 'bg-cyan-50 text-cyan-600'"
            >{{ entry.platform === 'B站' ? 'B' : 'N' }}</span>
            <span class="text-slate-600 truncate flex-1">{{ entry.title }}</span>
            <span class="text-slate-400 font-medium flex-shrink-0">{{ entry.hotValue }}</span>
          </div>
          <div class="flex items-center gap-2 pl-6 mt-0.5">
            <span class="text-slate-300 text-[10px]">{{ entry.publishTime }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue';
import * as echarts from 'echarts';
import type { DataCountDTO } from '../types';

const props = defineProps<{ dataCount?: DataCountDTO }>();

const hourlyChartRef = ref<HTMLElement | null>(null);
let hourlyChart: echarts.ECharts | null = null;

const renderHourlyChart = () => {
  if (!hourlyChartRef.value) return;
  const hd = props.dataCount?.hourlyData;
  if (!hd || hd.length === 0) return;

  if (hourlyChart) hourlyChart.dispose();
  hourlyChart = echarts.init(hourlyChartRef.value);

  const hours = hd.map(h => h.hour.padStart(2, '0') + ':00');

  hourlyChart.setOption({
    grid: { left: 3, right: 3, top: 6, bottom: 32 },
    xAxis: {
      type: 'category',
      data: hours,
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 9, interval: 1, rotate: 0 },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 9 },
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' } },
    },
    series: [{
      data: hd.map(h => h.count),
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#10b981', width: 1.5 },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(16, 185, 129, 0.2)' },
            { offset: 1, color: 'rgba(16, 185, 129, 0)' },
          ],
        },
      },
    }],
    animation: false,
  });
};

watch(() => props.dataCount?.hourlyData, () => {
  nextTick(renderHourlyChart);
}, { deep: true, immediate: true });

onUnmounted(() => {
  hourlyChart?.dispose();
});
</script>
