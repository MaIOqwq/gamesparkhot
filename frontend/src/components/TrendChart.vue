<template>
  <div class="relative glass-card p-5 sm:p-6">
    <div class="absolute -top-16 -right-16 w-32 h-32 bg-gradient-to-bl from-green-500/5 to-transparent rounded-full" />

    <div class="relative">
      <div class="flex items-center justify-between mb-1">
        <div class="flex items-center gap-2.5">
          <div class="w-1.5 h-5 rounded-full bg-gradient-to-b from-green-500 to-primary" />
          <h3 class="text-sm font-medium text-slate-500 tracking-wide">实时热度与预测</h3>
        </div>
        <div v-if="predictResult && showPrediction" class="flex items-center gap-2">
          <span class="text-xs text-slate-400">趋势</span>
          <span
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
            :class="trendBadgeClass(predictedTrendCode)"
          >
            <span class="w-1.5 h-1.5 rounded-full" :class="trendDotClass(predictedTrendCode)" />
            {{ predictedTrendLabel }}
          </span>
        </div>
      </div>
      <div class="glow-line mb-5" />

      <div v-if="loading" class="h-64 flex items-center justify-center">
        <div class="flex flex-col items-center gap-3">
          <div class="w-10 h-10 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          <span class="text-xs text-slate-400">加载中...</span>
        </div>
      </div>

      <div v-show="!loading" ref="chartRef" class="h-64" />

      <div v-if="!loading && trendData.length === 0" class="h-64 flex items-center justify-center">
        <div class="text-center">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-slate-200 mx-auto mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          <p class="text-sm text-slate-400">暂无趋势数据</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch, onUnmounted } from 'vue';
import * as echarts from 'echarts';
import { getTrendData, getPredictTrend } from '../api';
import type { TrendDTO, PredictDTO } from '../types';

const props = defineProps<{
  currentKeyword: string
  timeRange: string
}>();

const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;
let resizeFn: (() => void) | null = null;
const trendData = ref<TrendDTO[]>([]);
const predictResult = ref<PredictDTO | null>(null);
const loading = ref(true);

const predictedTrendCode = computed(() => predictResult.value?.trend_code ?? 2);
const predictedTrendLabel = computed(() => predictResult.value?.trend_label || predictResult.value?.trend || '平稳');
const predictedHot = computed(() => predictResult.value?.predicted_hot ?? predictResult.value?.predicted_hot_raw ?? null);
const showPrediction = computed(() => ['1d', '3d', '7d'].includes(props.timeRange));

const loadData = async () => {
  try {
    const response = await getTrendData(props.currentKeyword, props.timeRange);
    trendData.value = processDataByTimeWindow(response.data);
  } catch (error) {
    console.error('加载声量走势数据失败:', error);
  }

  try {
    const predictResponse = await getPredictTrend(props.currentKeyword);
    if (predictResponse.code === 200 && predictResponse.data) {
      predictResult.value = predictResponse.data;
    }
  } catch (error) {
    console.error('加载预测数据失败:', error);
  }
};

const processDataByTimeWindow = (data: TrendDTO[]): TrendDTO[] => {
  return data;
};

const renderChart = async () => {
  loading.value = false;
  await nextTick();
  if (chartRef.value && trendData.value.length > 0) {
    initChart();
  }
};

const trendBadgeClass = (code: number) => {
  switch (code) {
    case 4: return 'bg-red-50 text-red-600 border border-red-200';
    case 3: return 'bg-orange-50 text-orange-600 border border-orange-200';
    case 2: return 'bg-slate-50 text-slate-500 border border-slate-200';
    case 1: return 'bg-blue-50 text-blue-600 border border-blue-200';
    case 0: return 'bg-green-50 text-green-600 border border-green-200';
    default: return 'bg-slate-50 text-slate-500 border border-slate-200';
  }
};

const trendDotClass = (code: number) => {
  switch (code) {
    case 4: return 'bg-red-500';
    case 3: return 'bg-orange-500';
    case 2: return 'bg-slate-400';
    case 1: return 'bg-blue-500';
    case 0: return 'bg-green-500';
    default: return 'bg-slate-400';
  }
};

const buildMarkPoints = (trendList: TrendDTO[]) => {
  const points: any[] = [];
  for (let i = 0; i < trendList.length - 1; i++) {
    const item = trendList[i];
    if (item.topContents && item.topContents.length > 0) {
      const top1 = item.topContents[0];
      const ratio = top1.contributionRatio;
      let symbol = 'circle';
      let symbolSize = 10;
      let color = '#94a3b8';
      if (ratio > 30) {
        symbol = 'pin';
        symbolSize = 35;
        color = '#ef4444';
      } else if (ratio > 15) {
        symbol = 'circle';
        symbolSize = 10;
        color = '#f97316';
      }
      points.push({
        name: 'top_' + i,
        coord: [i, item.value],
        value: item.value,
        symbol,
        symbolSize,
        itemStyle: { color, borderColor: '#fff', borderWidth: 1 },
        label: ratio > 30 ? {
          color: '#fff',
          fontSize: 9,
          formatter: `${top1.title.length > 6 ? top1.title.substring(0, 6) + '..' : top1.title}`
        } : { show: false }
      });
    }
  }
  return points;
};

onMounted(async () => {
  await loadData();
  await renderChart();
});

watch(() => props.currentKeyword, async () => {
  loading.value = true;
  await loadData();
  await renderChart();
});

watch(() => props.timeRange, async () => {
  loading.value = true;
  await loadData();
  await renderChart();
});

const initChart = () => {
  if (!chartRef.value || trendData.value.length === 0) return;
  if (chart) chart.dispose();

  chart = echarts.init(chartRef.value);

  const labels = trendData.value.map(item => item.date);
  const allData = trendData.value.map(item => item.value);
  const actualData = showPrediction.value ? allData.slice(0, -1) : allData;

  let predictValue: number | null = null;
  let lastActual: number | null = null;
  if (showPrediction.value && actualData.length > 0) {
    lastActual = actualData[actualData.length - 1];
    const currentHot = predictResult.value?.current_hot;
    if (predictedHot.value != null && currentHot && currentHot > 0 && lastActual != null) {
      predictValue = Math.round(lastActual * (predictedHot.value / currentHot));
    } else {
      predictValue = predictedHot.value ?? (allData[allData.length - 1] ?? null);
    }
  }
  const predictPoint = predictValue;

  const predictData = new Array(labels.length).fill(null);
  if (predictValue !== null && showPrediction.value) {
    predictData[predictData.length - 1] = predictValue;
  }

  const markPoints = buildMarkPoints(trendData.value);

  const option = {
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: '#ffffff',
      borderColor: '#e2e8f0',
      borderWidth: 1,
      textStyle: { color: '#1e293b', fontSize: 12 },
      extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
      formatter: (params: any[]) => {
        if (!params || params.length === 0) return '';
        const param = params[0];
        const trendItem = trendData.value[param.dataIndex];
        let html = `<div style="font-weight:600;margin-bottom:4px;color:#1e293b">${param.axisValue}</div>`;
        html += `<div style="margin:2px 0">热度值: <span style="color:#1e293b;font-weight:500">${param.value}</span></div>`;
        if (trendItem && trendItem.topContents && trendItem.topContents.length > 0) {
          html += `<div style="border-top:1px solid #e2e8f0;margin:6px 0 4px;padding-top:4px;font-size:11px;color:#94a3b8">TOP内容</div>`;
          const top4 = trendItem.topContents.slice(0, 4);
          for (const tc of top4) {
            const platformColor = tc.platform === 'B站' ? '#3b82f6' : '#06b6d4';
            html += `<div style="display:flex;align-items:center;gap:4px;margin:3px 0;font-size:11px">
              <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${platformColor}"></span>
              <span style="color:#1e293b;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:160px">${tc.title}</span>
              <span style="color:#64748b">${tc.contributionRatio.toFixed(1)}%</span>
            </div>`;
          }
        }
        return html;
      }
    },
    legend: {
      data: showPrediction.value ? ['实际热度', '预测热度'] : ['实际热度'],
      textStyle: { color: '#64748b', fontSize: 12 },
      itemWidth: 12,
      itemHeight: 8,
      top: 0,
      right: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 28,
      containLabel: true
    },
    xAxis: {
      type: 'category' as const,
      boundaryGap: false,
      data: labels,
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#94a3b8', fontSize: 11 }
    },
    yAxis: {
      type: 'value' as const,
      scale: true,
      splitLine: { lineStyle: { color: '#f1f5f9', type: 'dashed' as const } },
      axisLabel: { color: '#94a3b8', fontSize: 11 }
    },
    series: [
      {
        name: '实际热度',
        data: actualData,
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: '#22c55e', width: 2.5 },
        itemStyle: { color: '#22c55e' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(34, 197, 94, 0.2)' },
              { offset: 1, color: 'rgba(34, 197, 94, 0.02)' }
            ]
          }
        },
        markPoint: markPoints.length > 0 ? {
          data: markPoints,
          animation: true
        } : undefined,
        animationDuration: 800,
        animationEasing: 'cubicOut' as const
      },
      ...(showPrediction.value ? [{
        name: '预测热度',
        data: predictData,
        type: 'line',
        smooth: true,
        showSymbol: false,
        symbol: 'diamond',
        symbolSize: 10,
        lineStyle: { color: '#3b82f6', width: 2.5, type: 'dashed' as const },
        itemStyle: { color: '#3b82f6' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59, 130, 246, 0.15)' },
              { offset: 1, color: 'rgba(59, 130, 246, 0.02)' }
            ]
          }
        },
        markLine: lastActual !== null && predictValue !== null ? {
          silent: true,
          symbol: ['none', 'none'],
          lineStyle: { color: '#3b82f6', width: 2.5, type: 'dashed' as const },
          label: { show: false },
          data: [[
            { coord: [labels.length - 2, lastActual] },
            { coord: [labels.length - 1, predictValue] }
          ]]
        } : undefined,
        animationDuration: 1000,
        animationEasing: 'cubicOut' as const,
        markPoint: predictPoint !== null ? {
          data: [{
            name: '预测峰值',
            coord: [labels.length - 1, predictPoint],
            value: predictPoint,
            symbol: 'pin',
            symbolSize: 40,
            itemStyle: { color: '#3b82f6' },
            label: { color: '#fff', fontSize: 11, fontWeight: 'bold' as const, formatter: `{c}` }
          }]
        } : undefined
      }] : [])
    ]
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
