// 核心指标数据类型
export interface MetricDTO {
  averageHotIndex: number;
  hotIndexChange: number;
  sentimentRatio: {
    positive: number;
    neutral: number;
    negative: number;
  };
  socialMediaRatio: number;
  traditionalMediaRatio: number;
  trendData: number[];
}

// 渠道分布数据类型
export interface ChannelDTO {
  channel: string;
  value: number;
}

// 地域数据类型
export interface RegionDTO {
  name: string;
  value: number;
}

// 声量走势数据类型
export interface TrendDTO {
  date: string;
  value: number;
  topContents?: TopContentDTO[];
}

// 热度归因内容类型
export interface TopContentDTO {
  title: string;
  platform: string;
  hotValue: number;
  contributionRatio: number;
}

// 渠道趋势类型（时间序列）
export interface ChannelTrendDTO {
  date: string;
  bilibiliValue: number;
  ngaValue: number;
  ngaRatio: number;
}

// 热词数据类型
export interface WordDTO {
  word: string;
  weight: number;
  sentimentScore?: number;
  hotTitle?: string;
  hotPlatform?: string;
  hotValue?: number;
}

// 舆情信息流数据类型
export interface InfoItemDTO {
  id: number;
  title: string;
  source: string;
  time: string;
  sentiment: 'positive' | 'neutral' | 'negative';
  hotValue: number;
  hotChange?: number;
  hotChangePercent?: number;
  trend?: 'up' | 'down' | 'stable';
}

// 预测结果类型
export interface PredictDTO {
  keyword: string;
  trend_code: number;
  trend_label?: string;
  predicted_hot?: number;
  current_hot?: number;
  change_rate?: number;
  strategy?: string;
  message?: string;
  trend?: string;
  probability?: number;
  predicted_hot_raw?: number;
  predicted_change_rate?: number;
  total_hot?: number;
  total_hot_raw?: number;
  window_start?: string;
  predict_window_start?: string;
  count?: number;
}

// API 响应类型
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}


// 预警面板类型
export interface WarningDTO {
  keyword: string;
  currentHot: number;
  changeRate: number;
  trend: string;
  trendCode: number;
  level: 'danger' | 'warning' | 'normal';
  message: string;
}

// 实时数据计数类型
export interface DataCountDTO {
  todayCount: number;
  last24hCount: number;
  totalCount: number;
  lastUpdateTime: string;
  hourlyData?: Array<{ hour: string; count: number }>;
  latestEntries?: Array<{
    title: string;
    platform: string;
    hotValue: number;
    publishTime: string;
  }>;
}

// 情绪焦点词条目
export interface SentimentWordItemDTO {
  word: string;
  weight: number;
  count: number;
}

// 情绪焦点词分组
export interface SentimentWordGroupDTO {
  sentiment: string;
  label: string;
  words: SentimentWordItemDTO[];
}

// 情感时间线类型
export interface SentimentTimelineDTO {
  date: string;
  positive: number;
  neutral: number;
  negative: number;
}

export interface AuthorDTO {
  author: string;
  contentCount: number;
  totalHot: number;
  avgHot: number;
}