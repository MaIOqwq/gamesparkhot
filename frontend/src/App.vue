<template>
  <div class="min-h-screen" style="background-color: #f1f5f9;">
    <!-- 顶部导航栏 -->
    <header class="sticky top-0 z-50 backdrop-blur-xl bg-white/90 border-b border-slate-200">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-16">
          <!-- 左侧：Logo -->
          <div class="flex items-center gap-2.5">
            <span class="text-sm font-semibold text-slate-500 whitespace-nowrap">
              舆情洞察分析板
            </span>
          </div>

          <!-- 中间：页面导航 -->
          <nav class="flex items-center gap-1 p-0.5 rounded-lg bg-slate-100 border border-slate-200">
            <button
              @click="activeTab = 'warnings'"
              class="px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
              :class="activeTab === 'warnings'
                ? 'bg-white text-slate-800 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'"
            >运营预警</button>
            <button
              @click="activeTab = 'analysis'"
              class="px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200"
              :class="activeTab === 'analysis'
                ? 'bg-white text-slate-800 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'"
            >关键词分析</button>
          </nav>

          <!-- 右侧：关键词选择 + 时间范围 -->
          <div class="flex items-center gap-3">

            <!-- 分析页控制区 -->
            <template v-if="activeTab === 'analysis'">
              <!-- 关键词切换下拉 -->
              <div class="relative">
                <button
                  @click="toggleKeywordDropdown"
                  class="group flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 border"
                  :class="showKeywordDropdown
                    ? 'bg-primary/10 text-primary border-primary/30'
                    : 'bg-white text-slate-600 border-slate-200 hover:border-primary/30 hover:text-primary'"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <span>{{ currentKeyword }}</span>
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-slate-400 group-hover:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                <!-- 关键词下拉菜单 -->
                <Transition name="dropdown">
                  <div
                    v-if="showKeywordDropdown"
                    class="absolute top-full left-0 mt-2 w-52 max-h-72 overflow-y-auto"
                  >
                    <div class="bg-white border border-slate-200 rounded-xl shadow-lg shadow-black/5 p-1.5">
                      <div
                        v-for="kw in warningKeywords"
                        :key="kw"
                        @click="switchKeyword(kw)"
                        class="px-3 py-2 rounded-lg text-xs cursor-pointer transition-all duration-150 flex items-center justify-between"
                        :class="kw === currentKeyword
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'"
                      >
                        <span>{{ kw }}</span>
                        <button
                          v-if="warningKeywords.length > 1"
                          @click.stop="removeKeyword(kw)"
                          class="w-4 h-4 flex items-center justify-center rounded-full text-slate-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                          title="删除关键词"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>

                      <!-- 添加分隔线 + 加号按钮 -->
                      <div class="border-t border-slate-100 mt-1 pt-1">
                        <button
                          @click="showAddList = !showAddList"
                          class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-slate-400 hover:text-primary hover:bg-primary/5 transition-all"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
                          </svg>
                          <span>添加关键词</span>
                        </button>

                        <!-- 可添加的关键词列表 -->
                        <Transition name="dropdown">
                          <div v-if="showAddList && availableKeywords.length > 0" class="mt-1 space-y-0.5 max-h-40 overflow-y-auto">
                            <button
                              v-for="kw in availableKeywords"
                              :key="kw"
                              @click="addWarningKeyword(kw)"
                              class="w-full text-left px-3 py-1.5 rounded-lg text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-50 transition-all"
                            >+ {{ kw }}</button>
                          </div>
                          <div v-else-if="showAddList" class="text-xs text-slate-300 text-center py-2">已添加全部关键词</div>
                        </Transition>
                      </div>
                    </div>
                  </div>
                </Transition>
              </div>

              <!-- 时间范围按钮组 -->
              <nav class="hidden md:flex items-center gap-1 p-0.5 rounded-lg bg-slate-100 border border-slate-200" role="tablist">
                <button
                  v-for="option in timeRangeOptions"
                  :key="option.value"
                  @click="changeTimeRange(option.value)"
                  :class="[
                    'px-2.5 py-1 text-xs font-medium rounded-md transition-all duration-200',
                    timeRange === option.value
                      ? 'bg-primary text-white shadow-sm shadow-primary/20'
                      : 'text-slate-500 hover:text-slate-700'
                  ]"
                  role="tab"
                  :aria-selected="timeRange === option.value"
                >
                  {{ option.label }}
                </button>
              </nav>

              <!-- 移动端时间范围下拉 -->
              <div class="md:hidden relative">
                <select
                  @change="changeTimeRange(($event.target as HTMLSelectElement).value)"
                  class="appearance-none bg-white border border-slate-200 text-slate-600 text-xs px-2 py-1.5 rounded-lg pr-7 focus:outline-none focus:border-primary/40"
                >
                  <option v-for="option in timeRangeOptions" :key="option.value" :value="option.value" :selected="timeRange === option.value" class="bg-white">
                    {{ option.label }}
                  </option>
                </select>
              </div>
            </template>
          </div>
        </div>
      </div>
    </header>

    <!-- ====== 运营预警主页 ====== -->
    <main v-if="activeTab === 'warnings'" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
      <div class="mb-4">
        <h1 class="text-lg font-semibold text-slate-700">运营预警面板</h1>
        <p class="text-xs text-slate-400 mt-0.5">选择关键词查看预警</p>
      </div>

      <!-- 已选监控关键词（大号展示） -->
      <div class="flex flex-wrap items-center gap-2 mb-4 min-h-[2.5rem]">
        <span
          v-for="kw in warningKeywords"
          :key="kw"
          class="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg bg-rose-50 text-rose-600 border border-rose-200 font-medium shadow-sm"
        >
          {{ kw }}
          <button @click="toggleWarningKeyword(kw)" class="hover:text-rose-800 transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </span>
        <span v-if="warningKeywords.length === 0" class="text-sm text-slate-300 italic">点击下方 + 添加监控关键词</span>
      </div>

      <!-- 蓝色加号 → 预警面板上方 -->
      <div class="flex items-center gap-3 mb-4">
        <button
          @click="openKeywordModal"
          class="w-10 h-10 rounded-xl bg-primary/10 border-2 border-dashed border-primary/30 hover:bg-primary/15 hover:border-primary/50 transition-all flex items-center justify-center group"
          title="添加监控关键词"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-primary/60 group-hover:text-primary transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </button>
        <span class="text-xs text-slate-400">点击添加监控关键词</span>
      </div>

      <!-- 双栏布局：左预警 + 右概览 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div class="lg:col-span-2">
          <WarningPanel :warnings="filteredWarnings" />
        </div>
        <div class="lg:col-span-1">
          <DataOverview :dataCount="dataCount" />
        </div>
      </div>

      <!-- 关键词选择模态框 -->
      <Teleport to="body">
        <Transition name="dropdown">
          <div
            v-if="showKeywordModal"
            class="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm p-4"
            @click.self="closeKeywordModal"
          >
            <div class="bg-white rounded-2xl shadow-2xl shadow-black/10 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
              <!-- 标题栏 -->
              <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                <h2 class="text-sm font-semibold text-slate-700">选择监控关键词</h2>
                <button @click="closeKeywordModal" class="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
              <!-- 关键词卡片网格 -->
              <div class="flex-1 overflow-y-auto p-5">
                <div v-if="loadingKeywordMetrics" class="flex items-center justify-center py-16">
                  <div class="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                </div>
                <div v-else class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div
                    v-for="kw in allKeywords"
                    :key="kw"
                    @click="toggleWarningKeyword(kw)"
                    class="relative rounded-xl border-2 p-3.5 cursor-pointer transition-all duration-150"
                    :class="warningKeywords.includes(kw)
                      ? 'border-primary bg-primary/5 shadow-sm shadow-primary/10'
                      : 'border-slate-200 bg-white hover:border-primary/30 hover:shadow-sm'"
                  >
                    <!-- 已选标记 -->
                    <div v-if="warningKeywords.includes(kw)" class="absolute top-2 right-2 w-5 h-5 rounded-full bg-primary text-white flex items-center justify-center">
                      <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" /></svg>
                    </div>
                    <!-- 关键词名称 -->
                    <div class="text-sm font-medium text-slate-700 mb-2 pr-5">{{ kw }}</div>
                    <!-- 热度和趋势 -->
                    <div class="flex items-center gap-2">
                      <span class="text-lg font-bold" :class="getTrendClass(keywordMetrics[kw])">{{ keywordMetrics[kw] ? keywordMetrics[kw].averageHotIndex.toFixed(1) : '--' }}</span>
                      <span
                        v-if="keywordMetrics[kw]"
                        class="text-xs font-medium px-1.5 py-0.5 rounded-full"
                        :class="getTrendBadgeClass(keywordMetrics[kw])"
                      >
                        {{ getTrendLabel(keywordMetrics[kw]) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Transition>
      </Teleport>
    </main>

    <!-- ====== 关键词分析页 ====== -->
    <main v-else class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
      <template v-if="warningKeywords.length === 0">
        <div class="flex flex-col items-center justify-center py-20">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-16 h-16 text-slate-200 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
            <path stroke-linecap="round" stroke-linejoin="round" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
          </svg>
          <p class="text-sm text-slate-400 mb-4">暂无关键词，请先在运营预警页面选择关键词</p>
          <button
            @click="activeTab = 'warnings'"
            class="text-xs px-4 py-2 rounded-lg bg-primary text-white font-medium hover:bg-primary/90 transition-colors"
          >前往运营预警</button>
        </div>
      </template>

      <template v-else>
        <!-- 核心指标卡片区 -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 mb-6">
          <MetricCard
            title="平均热度指数"
            :value="metrics.averageHotIndex"
            :change="metrics.hotIndexChange"
          />
          <MetricCard
            title="情感分布"
            :sentimentData="metrics.sentimentRatio"
          />
        </div>

        <!-- 可视化图表区 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 mb-6">
          <ChannelChart :currentKeyword="currentKeyword" :timeRange="timeRange" />
          <TrendChart :currentKeyword="currentKeyword" :timeRange="timeRange" />
          <div class="lg:col-span-2">
            <WordCloudSim :currentKeyword="currentKeyword" :timeRange="timeRange" />
          </div>
        </div>


        <!-- 实时热度列表 + 作者排行 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6 mb-6">
          <InfoList :currentKeyword="currentKeyword" :timeRange="timeRange" />
          <AuthorRanking :currentKeyword="currentKeyword" :timeRange="timeRange" />
        </div>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue';
import MetricCard from './components/MetricCard.vue';
import ChannelChart from './components/ChannelChart.vue';
import TrendChart from './components/TrendChart.vue';
import WordCloudSim from './components/WordCloudSim.vue';
import InfoList from './components/InfoList.vue';
import WarningPanel from './components/WarningPanel.vue';
import DataOverview from './components/DataOverview.vue';
import AuthorRanking from './components/AuthorRanking.vue';
import { getMetrics, getWarnings, getDataCount, getAllKeywords } from './api';
import type { WarningDTO, DataCountDTO } from './types';

// ====== 页面状态 ======
const activeTab = ref<'warnings' | 'analysis'>('warnings');

// ====== 预警关键词管理（与分析关键词独立） ======
const WARN_KEYWORDS_KEY = 'warning-keywords';
const loadWarningKeywords = (): string[] => {
  try {
    const saved = localStorage.getItem(WARN_KEYWORDS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {}
  return ['手机游戏'];
};
const saveWarningKeywords = (kws: string[]) => {
  localStorage.setItem(WARN_KEYWORDS_KEY, JSON.stringify(kws));
};

const warningKeywords = ref<string[]>(loadWarningKeywords());

const toggleWarningKeyword = (kw: string) => {
  const idx = warningKeywords.value.indexOf(kw);
  if (idx >= 0) {
    warningKeywords.value.splice(idx, 1);
  } else {
    warningKeywords.value.push(kw);
  }
  saveWarningKeywords(warningKeywords.value);
};

// 基于预警关键词过滤
const filteredWarnings = computed(() => {
  if (warningKeywords.value.length === 0) return [];
  return warnings.value.filter(w => warningKeywords.value.includes(w.keyword));
});
const currentKeyword = ref(warningKeywords.value[0] || '手机游戏');
const showKeywordDropdown = ref(false);
const showAddList = ref(false);

const availableKeywords = computed(() =>
  allKeywords.value.filter(kw => !warningKeywords.value.includes(kw))
);

const addWarningKeyword = (kw: string) => {
  if (!warningKeywords.value.includes(kw)) {
    warningKeywords.value.push(kw);
    saveWarningKeywords(warningKeywords.value);
  }
};

const removeKeyword = (kw: string) => {
  if (warningKeywords.value.length <= 1) return;
  warningKeywords.value = warningKeywords.value.filter(k => k !== kw);
  saveWarningKeywords(warningKeywords.value);
  if (currentKeyword.value === kw) {
    currentKeyword.value = warningKeywords.value[0];
    updateDataForKeyword(currentKeyword.value);
  }
};

const switchKeyword = (keyword: string) => {
  if (keyword === currentKeyword.value) {
    showKeywordDropdown.value = false;
    return;
  }
  currentKeyword.value = keyword;
  showKeywordDropdown.value = false;
  updateDataForKeyword(keyword);
};

const toggleKeywordDropdown = () => {
  showKeywordDropdown.value = !showKeywordDropdown.value;
  if (!showKeywordDropdown.value) showAddList.value = false;
};

const handleClickOutside = (e: MouseEvent) => {
  const target = e.target as HTMLElement;
  if (showKeywordDropdown.value && !target.closest('.relative')) {
    showKeywordDropdown.value = false;
    showAddList.value = false;
  }
};


// ====== 时间范围 ======
const timeRangeOptions = [
  { label: '1天', value: '1d' },
  { label: '3天', value: '3d' },
  { label: '7天', value: '7d' },
  { label: '1月', value: '1m' },
  { label: '3月', value: '3m' },
  { label: '6月', value: '6m' },
  { label: '1年', value: '1y' },
  { label: '全部', value: 'all' },
];
const timeRange = ref('7d');

const changeTimeRange = (value: string) => {
  timeRange.value = value;
  updateDataForKeyword(currentKeyword.value);
};

// ====== 指标数据 ======
interface SentimentRatio {
  positive: number;
  neutral: number;
  negative: number;
}
interface MetricsData {
  averageHotIndex: number;
  hotIndexChange: number;
  sentimentRatio: SentimentRatio;
  trendData: number[];
}

const metrics = reactive<MetricsData>({
  averageHotIndex: 0,
  hotIndexChange: 0,
  sentimentRatio: { positive: 0, neutral: 0, negative: 0 },
  trendData: [],
});

const warnings = ref<WarningDTO[]>([]);
const allKeywords = ref<string[]>([]);

// ====== 关键词选择模态框 ======
interface KeywordMetric {
  averageHotIndex: number;
  hotIndexChange: number;
}
const showKeywordModal = ref(false);
const loadingKeywordMetrics = ref(false);
const keywordMetrics = reactive<Record<string, KeywordMetric>>({});

const getTrendLabel = (m: KeywordMetric): string => {
  if (m.averageHotIndex < 1) return '下降';
  if (m.hotIndexChange < -5) return '下降';
  if (m.hotIndexChange > 5) return '上升';
  return '平稳';
};
const getTrendClass = (m?: KeywordMetric): string => {
  if (!m) return 'text-slate-300';
  const label = getTrendLabel(m);
  if (label === '上升') return 'text-emerald-600';
  if (label === '下降') return 'text-red-500';
  return 'text-slate-500';
};
const getTrendBadgeClass = (m: KeywordMetric): string => {
  const label = getTrendLabel(m);
  if (label === '上升') return 'bg-emerald-50 text-emerald-600 border border-emerald-200';
  if (label === '下降') return 'bg-red-50 text-red-500 border border-red-200';
  return 'bg-slate-50 text-slate-500 border border-slate-200';
};

const openKeywordModal = async () => {
  showKeywordModal.value = true;
  if (Object.keys(keywordMetrics).length > 0) return; // 已有缓存
  loadingKeywordMetrics.value = true;
  try {
    const results = await Promise.all(
      allKeywords.value.map(kw =>
        getMetrics(kw, '7d').then(r => ({ kw, data: r.data }))
      )
    );
    for (const { kw, data } of results) {
      if (data) keywordMetrics[kw] = { averageHotIndex: data.averageHotIndex, hotIndexChange: data.hotIndexChange };
    }
  } catch (e) {
    console.error('获取关键词指标失败:', e);
  } finally {
    loadingKeywordMetrics.value = false;
  }
};
const closeKeywordModal = () => {
  showKeywordModal.value = false;
};

let abortController: AbortController | null = null;

const updateDataForKeyword = async (keyword: string) => {
  // 取消上一次未完成的请求
  if (abortController) abortController.abort();
  abortController = new AbortController();
  const signal = abortController.signal;

  try {
    const metricsResponse = await getMetrics(keyword, timeRange.value, signal);
    if (metricsResponse.code === 200 && metricsResponse.data) {
      const data = metricsResponse.data;
      metrics.averageHotIndex = data.averageHotIndex;
      metrics.hotIndexChange = data.hotIndexChange;
      metrics.sentimentRatio = data.sentimentRatio;
      metrics.trendData = data.trendData;
    }
  } catch (error: any) {
    if (error?.name !== 'CanceledError') console.error('获取指标数据失败:', error);
  }

  try {
    const warningResponse = await getWarnings('1d', signal);
    if (warningResponse.code === 200 && warningResponse.data) {
      warnings.value = warningResponse.data;
    }
  } catch (error: any) {
    if (error?.response?.status === 404) {
      console.warn('预警接口暂未部署');
    } else if (error?.name !== 'CanceledError') {
      console.error('获取预警数据失败:', error);
    }
  }
};

// ====== 实时数据计数 ======
const dataCount = reactive<DataCountDTO>({
  todayCount: 0,
  last24hCount: 0,
  totalCount: 0,
  lastUpdateTime: '',
});

let dataCountTimer: ReturnType<typeof setInterval> | null = null;

const fetchDataCount = async () => {
  try {
    const response = await getDataCount();
    if (response.code === 200 && response.data) {
      dataCount.todayCount = response.data.todayCount;
      dataCount.last24hCount = response.data.last24hCount;
      dataCount.totalCount = response.data.totalCount;
      dataCount.lastUpdateTime = response.data.lastUpdateTime;
      dataCount.hourlyData = response.data.hourlyData;
      dataCount.latestEntries = response.data.latestEntries;
    }
  } catch (error) {
    console.error('获取数据计数失败:', error);
  }
};

onMounted(async () => {
  document.addEventListener('click', handleClickOutside);
  fetchDataCount();
  dataCountTimer = setInterval(fetchDataCount, 30000);
  updateDataForKeyword(currentKeyword.value);

  // 获取全量关键词
  try {
    const res = await getAllKeywords();
    if (res.code === 200 && res.data) {
      allKeywords.value = res.data;
    }
  } catch (e) {
    console.error('获取关键词列表失败:', e);
  }
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
  if (dataCountTimer) {
    clearInterval(dataCountTimer);
    dataCountTimer = null;
  }
});
</script>

<style>
/* 下拉菜单过渡动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.96);
}
</style>
