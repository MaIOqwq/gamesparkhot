<template>
  <div class="relative glass-card p-5 sm:p-6">
    <div class="absolute -top-16 -right-16 w-32 h-32 bg-gradient-to-bl from-violet-500/5 to-transparent rounded-full" />

    <div class="relative">
      <div class="flex items-center justify-between mb-1">
        <div class="flex items-center gap-2.5">
          <div class="w-1.5 h-5 rounded-full bg-gradient-to-b from-violet-500 to-purple-500" />
          <h3 class="text-sm font-medium text-slate-500 tracking-wide">高影响力作者</h3>
        </div>
        <span class="text-xs text-slate-400">按总热度排序 TOP20</span>
      </div>
      <div class="glow-line mb-5" />

      <div v-if="loading" class="flex items-center justify-center py-12">
        <div class="w-8 h-8 border-2 border-violet-300 border-t-violet-500 rounded-full animate-spin" />
      </div>

      <div v-else-if="authors.length === 0" class="py-8 text-center text-sm text-slate-400">
        暂无数据
      </div>

      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-xs text-slate-400 uppercase tracking-wide">
              <th class="pb-3 pr-2 font-medium w-10">#</th>
              <th class="pb-3 pr-2 font-medium">作者</th>
              <th class="pb-3 pr-2 font-medium text-right">内容数</th>
              <th class="pb-3 pr-2 font-medium text-right">总热度</th>
              <th class="pb-3 font-medium text-right">平均热度</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(a, i) in authors"
              :key="a.author"
              class="border-t border-slate-50 hover:bg-slate-50/50 transition-colors"
            >
              <td class="py-2.5 pr-2">
                <span
                  class="inline-flex items-center justify-center w-5 h-5 rounded text-xs font-bold"
                  :class="rankClass(i)"
                >{{ i + 1 }}</span>
              </td>
              <td class="py-2.5 pr-2 font-medium text-slate-700 truncate max-w-[140px]">{{ a.author }}</td>
              <td class="py-2.5 pr-2 text-right text-slate-600">{{ a.contentCount }}</td>
              <td class="py-2.5 pr-2 text-right font-medium text-slate-700">{{ formatNum(a.totalHot) }}</td>
              <td class="py-2.5 text-right text-slate-500">{{ formatNum(a.avgHot) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { getAuthorRanking } from '../api';
import type { AuthorDTO } from '../types';

const props = defineProps<{
  currentKeyword: string
  timeRange: string
}>();

const authors = ref<AuthorDTO[]>([]);
const loading = ref(true);

const loadData = async () => {
  loading.value = true;
  try {
    const response = await getAuthorRanking(props.currentKeyword, props.timeRange);
    if (response.code === 200 && response.data) {
      authors.value = response.data;
    }
  } catch (error) {
    console.error('加载作者排行失败:', error);
  } finally {
    loading.value = false;
  }
};

const rankClass = (i: number) => {
  if (i === 0) return 'bg-amber-100 text-amber-700';
  if (i === 1) return 'bg-slate-200 text-slate-600';
  if (i === 2) return 'bg-orange-100 text-orange-700';
  return 'bg-slate-100 text-slate-400';
};

const formatNum = (n: number): string => {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(Math.floor(n));
};

watch([() => props.currentKeyword, () => props.timeRange], () => {
  loadData();
}, { immediate: true });
</script>
