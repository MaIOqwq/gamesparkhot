<template>
  <div class="data-provider">
    <div class="control-panel">
      <input
        type="text"
        v-model="keyword"
        placeholder="输入关键词"
        @input="handleKeywordChange"
        class="keyword-input"
      />
      <select v-model="timeRange" @change="handleTimeRangeChange" class="time-range-select">
        <option value="1d">1天</option>
        <option value="3d">3天</option>
        <option value="7d">7天</option>
        <option value="1m">1个月</option>
        <option value="3m">3个月</option>
        <option value="1y">1年</option>
      </select>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else class="card-container">
      <div class="card">
        <h3>核心指标</h3>
        <div class="metric-item">
          <span class="label">平均热度指数:</span>
          <span class="value">{{ Math.round(metrics.averageHotIndex) }}</span>
        </div>
        <div class="metric-item">
          <span class="label">热度变化:</span>
          <span class="value">{{ metrics.hotIndexChange }}%</span>
        </div>
        <div class="sentiment-ratio">
          <span>情感比例: </span>
          <span>正面 {{ metrics.sentimentRatio.positive }}%</span>
          <span>中性 {{ metrics.sentimentRatio.neutral }}%</span>
          <span>负面 {{ metrics.sentimentRatio.negative }}%</span>
        </div>
      </div>

      <div class="card">
        <h3>渠道分布</h3>
        <ul>
          <li v-for="item in channelData" :key="item.channel">
            {{ item.channel }}: {{ item.value }}%
          </li>
        </ul>
      </div>

      <div class="card">
        <h3>声量走势</h3>
        <ul>
          <li v-for="item in trendData" :key="item.date">
            {{ item.date }}: {{ item.value }}
          </li>
        </ul>
      </div>

      <div class="card">
        <h3>热词</h3>
        <ul>
          <li v-for="item in wordsData" :key="item.word">
            {{ item.word }} ({{ item.weight }})
          </li>
        </ul>
      </div>

      <div class="card">
        <h3>舆情信息</h3>
        <ul>
          <li v-for="item in infoList" :key="item.id">
            <div class="info-title">{{ item.title }}</div>
            <div class="info-meta">
              <span>{{ item.source }}</span>
              <span>{{ item.time }}</span>
              <span :class="['sentiment', item.sentiment]">{{ item.sentiment }}</span>
              <span>热度: {{ item.hotValue }}</span>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { getMetrics, getChannelData, getTrendData, getWordsData, getInfoList } from '../api';
import type { MetricDTO, ChannelDTO, TrendDTO, WordDTO, InfoItemDTO } from '../types';

const keyword = ref('');
const timeRange = ref('7d');
const loading = ref(false);
const metrics = ref<MetricDTO>({
  averageHotIndex: 0,
  hotIndexChange: 0,
  sentimentRatio: { positive: 0, neutral: 0, negative: 0 },
  socialMediaRatio: 0,
  traditionalMediaRatio: 0,
  trendData: []
});
const channelData = ref<ChannelDTO[]>([]);
const trendData = ref<TrendDTO[]>([]);
const wordsData = ref<WordDTO[]>([]);
const infoList = ref<InfoItemDTO[]>([]);

const fetchData = async () => {
  loading.value = true;
  const kw = keyword.value || undefined;
  const tr = timeRange.value;
  try {
    const [metricsRes, channelRes, trendRes, wordsRes, listRes] = await Promise.all([
      getMetrics(kw, tr),
      getChannelData(kw, tr),
      getTrendData(kw, tr),
      getWordsData(kw, tr),
      getInfoList(kw, tr)
    ]);
    if (metricsRes.code === 200) metrics.value = metricsRes.data;
    if (channelRes.code === 200) channelData.value = channelRes.data;
    if (trendRes.code === 200) trendData.value = trendRes.data;
    if (wordsRes.code === 200) wordsData.value = wordsRes.data;
    if (listRes.code === 200) infoList.value = listRes.data;
  } catch (error) {
    console.error('获取数据失败:', error);
  } finally {
    loading.value = false;
  }
};

const handleKeywordChange = () => { fetchData(); };
const handleTimeRangeChange = () => { fetchData(); };

onMounted(() => { fetchData(); });
</script>

<style scoped>
.data-provider {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}
.control-panel {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.keyword-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
}
.time-range-select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
}
.loading {
  text-align: center;
  padding: 40px;
  font-size: 18px;
  color: #666;
}
.card-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}
.card {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.card h3 {
  margin-top: 0;
  margin-bottom: 16px;
  font-size: 16px;
  color: #333;
  border-bottom: 1px solid #eee;
  padding-bottom: 8px;
}
.metric-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}
.sentiment-ratio { margin-top: 12px; font-size: 14px; }
.sentiment-ratio span { margin-right: 12px; }
ul { list-style: none; padding: 0; margin: 0; }
li { padding: 8px 0; border-bottom: 1px solid #f0f0f0; }
li:last-child { border-bottom: none; }
.info-title { font-weight: 500; margin-bottom: 4px; }
.info-meta { font-size: 12px; color: #666; display: flex; gap: 12px; }
.sentiment { padding: 2px 6px; border-radius: 10px; font-size: 10px; }
.sentiment.positive { background: #e6f7ee; color: #13c2c2; }
.sentiment.neutral { background: #f6ffed; color: #52c41a; }
.sentiment.negative { background: #fff2f0; color: #ff4d4f; }
</style>
