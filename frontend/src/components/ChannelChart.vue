<template>
  <div class="relative glass-card p-5 sm:p-6">
    <div class="absolute -bottom-16 -left-16 w-32 h-32 bg-gradient-to-tr from-secondary/5 to-transparent rounded-full" />

    <div class="relative">
      <div class="flex items-center gap-2.5 mb-1">
        <div class="w-1.5 h-5 rounded-full bg-gradient-to-b from-primary to-secondary" />
        <h3 class="text-sm font-medium text-slate-500 tracking-wide">渠道趋势占比</h3>
      </div>
      <div class="glow-line mb-5" />

      <div class="relative h-64">
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-white/60 z-10">
          <div class="flex flex-col items-center gap-3">
            <div class="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            <span class="text-xs text-slate-400">加载中...</span>
          </div>
        </div>
        <div ref="chartRef" class="h-64 w-full"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted, nextTick } from 'vue';
import * as echarts from 'echarts';
import { getChannelData } from '../api';
import type { ChannelDTO } from '../types';

const props = defineProps<{ currentKeyword: string; timeRange: string }>();

const chartRef = ref<HTMLElement | null>(null);
const loading = ref(true);
let chart: echarts.ECharts | null = null;

const renderChart = async () => {
  loading.value = true;
  try {
    const response = await getChannelData(props.currentKeyword, props.timeRange);
    if (response.code !== 200 || !response.data || response.data.length === 0) return;

    const data: ChannelDTO[] = response.data;
    if (!chartRef.value) return;

    if (chart) chart.dispose();
    chart = echarts.init(chartRef.value);

    chart.setOption({
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: '#e2e8f0',
        borderWidth: 1,
        textStyle: { fontSize: 12, color: '#334155' },
        formatter: (params: any) => {
          return `<div class="text-xs">
            <span class="font-medium">${params.name}</span><br/>
            占比: <strong>${params.percent}%</strong>
          </div>`;
        },
      },
      legend: {
        bottom: 0,
        left: 'center',
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { fontSize: 11, color: '#64748b' },
      },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 6,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: (params: any) => `${params.name}\n${params.percent}%`,
          fontSize: 11,
          color: '#64748b',
        },
        emphasis: {
          label: { show: true, fontSize: 13, fontWeight: 'bold' },
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.15)' },
        },
        data: data.map((d: ChannelDTO) => ({
          name: d.channel,
          value: d.value,
          itemStyle: {
            color: d.channel === 'B站' ? '#3b82f6' : d.channel === 'NGA' ? '#06b6d4' : '#94a3b8',
          },
        })),
      }],
    });
  } catch (error) {
    console.error('渠道占比加载失败:', error);
  } finally {
    loading.value = false;
  }
};

watch(() => [props.currentKeyword, props.timeRange], () => {
  nextTick(renderChart);
});

onMounted(() => {
  renderChart();
});

onUnmounted(() => {
  chart?.dispose();
  chart = null;
});
</script>
