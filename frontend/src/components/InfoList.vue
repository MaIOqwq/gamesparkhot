<template>
  <div class="relative glass-card p-5 sm:p-6">
    <!-- 装饰 -->
    <div class="absolute -top-16 -left-16 w-32 h-32 bg-gradient-to-br from-amber-500/5 to-transparent rounded-full" />

    <div class="relative">
      <div class="flex items-center justify-between mb-1">
        <div class="flex items-center gap-2.5">
          <div class="w-1.5 h-5 rounded-full bg-gradient-to-b from-amber-500 to-orange-500" />
          <h3 class="text-sm font-medium text-slate-500 tracking-wide">实时热度排行榜</h3>
        </div>
        <span class="status-dot bg-green-500" />
      </div>
      <div class="glow-line mb-5" />

      <!-- 加载状态 -->
      <div v-if="loading" class="space-y-3">
        <div v-for="i in 4" :key="i" class="p-4 rounded-lg skeleton" style="height: 72px" />
      </div>

      <!-- 列表 -->
      <TransitionGroup v-else name="list" tag="div" class="space-y-3">
        <div
          v-for="(item, index) in infoList"
          :key="`${item.id}-${item.hotValue}`"
          class="group relative overflow-hidden rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition-all duration-300 hover:border-slate-300 cursor-pointer"
        >
          <!-- 排名指示器 -->
          <div class="absolute left-0 top-0 bottom-0 w-0.5 transition-all duration-300"
            :class="{
              'bg-gradient-to-b from-amber-400 to-amber-600': index === 0,
              'bg-gradient-to-b from-slate-300 to-slate-400': index === 1,
              'bg-gradient-to-b from-orange-400 to-orange-600': index === 2,
              'bg-slate-200 group-hover:bg-slate-300': index > 2
            }"
          />

          <div class="p-4 pl-5">
            <div class="flex items-start justify-between gap-3">
              <!-- 标题区域 -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2.5 mb-2">
                  <!-- 排名标签 -->
                  <span
                    class="inline-flex items-center justify-center w-5 h-5 rounded text-xs font-bold shrink-0"
                    :class="{
                      'bg-amber-100 text-amber-700': index === 0,
                      'bg-slate-200 text-slate-600': index === 1,
                      'bg-orange-100 text-orange-700': index === 2,
                      'bg-slate-100 text-slate-400': index > 2
                    }"
                  >
                    {{ index + 1 }}
                  </span>
                  <h4 class="font-medium text-sm text-slate-700 truncate group-hover:text-slate-900 transition-colors">
                    {{ item.title }}
                  </h4>
                </div>

                <!-- 元信息 -->
                <div class="flex items-center gap-3 text-xs text-slate-400 ml-7">
                  <span class="flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                    {{ item.source }}
                  </span>
                  <span class="flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {{ item.time }}
                  </span>
                </div>
              </div>

              <!-- 标签和热度 -->
              <div class="flex flex-col items-end gap-2 shrink-0">
                <!-- 趋势箭头 -->
                <span v-if="item.trend" class="inline-flex items-center gap-0.5 text-xs font-medium"
                  :class="{
                    'text-green-500': item.trend === 'up',
                    'text-red-500': item.trend === 'down',
                    'text-slate-300': item.trend === 'stable'
                  }"
                >
                  <template v-if="item.trend === 'up'">↑</template>
                  <template v-else-if="item.trend === 'down'">↓</template>
                  <template v-else>→</template>
                  <span v-if="item.hotChangePercent !== undefined" class="text-[10px]">
                    {{ item.trend === 'up' ? '+' : '' }}{{ item.hotChangePercent?.toFixed(1) }}%
                  </span>
                </span>
                <span
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border"
                  :class="{
                    'bg-green-50 text-green-600 border-green-200': item.sentiment === 'positive',
                    'bg-yellow-50 text-yellow-600 border-yellow-200': item.sentiment === 'neutral',
                    'bg-red-50 text-red-600 border-red-200': item.sentiment === 'negative'
                  }"
                >
                  <span class="w-1 h-1 rounded-full"
                    :class="{
                      'bg-green-500': item.sentiment === 'positive',
                      'bg-yellow-500': item.sentiment === 'neutral',
                      'bg-red-500': item.sentiment === 'negative'
                    }"
                  />
                  {{ item.sentiment === 'positive' ? '正面' : item.sentiment === 'neutral' ? '中性' : '负面' }}
                </span>

                <!-- 热度值 -->
                <div class="flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-amber-500" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M12.395 2.553a1 1 0 00-1.45-.385c-.345.23-.614.558-.822.88-.214.33-.403.713-.57 1.116-.334.804-.614 1.768-.84 2.734a31.365 31.365 0 00-.613 3.58 2.64 2.64 0 01-.945-1.067c-.328-.68-.398-1.534-.398-2.654A1 1 0 005.05 6.05 6.981 6.981 0 003 11a7 7 0 1011.95-4.95c-.592-.591-.98-.985-1.348-1.467-.363-.476-.724-1.063-1.207-2.03zM12.12 15.12A3 3 0 017 13s.879.5 2.5.5c0-1 .5-4 1.25-4.5.5 1 .786 1.293 1.371 1.879A2.99 2.99 0 0113 13a2.99 2.99 0 01-.879 2.121z" clip-rule="evenodd" />
                  </svg>
                  <span class="text-xs font-semibold text-amber-600">{{ item.hotValue }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- 空状态 -->
      <div v-if="!loading && infoList.length === 0" class="py-12 text-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 text-slate-200 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
        </svg>
        <p class="text-sm text-slate-400">暂无热点信息</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { getInfoList } from '../api';
import type { InfoItemDTO } from '../types';

const props = defineProps<{
  currentKeyword: string
  timeRange: string
}>();

const infoList = ref<InfoItemDTO[]>([]);
const loading = ref(true);

const loadData = async () => {
  try {
    const response = await getInfoList(props.currentKeyword, props.timeRange);
    infoList.value = response.data.slice(0, 6);
  } catch (error) {
    console.error('加载信息流数据失败:', error);
    infoList.value = [];
  }
};

onMounted(async () => {
  await loadData();
  loading.value = false;
});

watch(() => [props.currentKeyword, props.timeRange], async () => {
  loading.value = true;
  try {
    await loadData();
  } finally {
    loading.value = false;
  }
});
</script>
