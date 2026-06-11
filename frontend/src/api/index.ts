import axios from 'axios';
import type { MetricDTO, ChannelDTO, ChannelTrendDTO, TrendDTO, WordDTO, InfoItemDTO, ApiResponse, PredictDTO, WarningDTO, SentimentTimelineDTO, DataCountDTO, SentimentWordGroupDTO, AuthorDTO } from '../types';

const api = axios.create({
  baseURL: '',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json'
  }
});

export const getMetrics = async (keyword?: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<MetricDTO>> => {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/metrics?${params.toString()}`, { signal });
  return response.data;
};


export const getChannelData = async (keyword?: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<ChannelDTO[]>> => {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/channel?${params.toString()}`, { signal });
  return response.data;
};

export const getChannelTrend = async (keyword?: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<ChannelTrendDTO[]>> => {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/channel-trend?${params.toString()}`, { signal });
  return response.data;
};

export const getPredictTrend = async (keyword: string, signal?: AbortSignal): Promise<ApiResponse<PredictDTO>> => {
  const response = await api.get(`/api/predict/trend?keyword=${encodeURIComponent(keyword)}`, { signal });
  return response.data;
};

export const getTrendData = async (keyword?: string, timeRange?: string, signal?: AbortSignal): Promise<ApiResponse<TrendDTO[]>> => {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  if (timeRange) params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/trend?${params.toString()}`, { signal });
  return response.data;
};

export const getWordsData = async (keyword?: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<WordDTO[]>> => {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/words?${params.toString()}`, { signal });
  return response.data;
};

export const getInfoList = async (keyword?: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<InfoItemDTO[]>> => {
  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/list?${params.toString()}`, { signal });
  return response.data;
};

export const getWarnings = async (timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<WarningDTO[]>> => {
  const response = await api.get(`/api/opinion/warnings?timeRange=${timeRange}`, { signal });
  return response.data;
};

export const getDataCount = async (signal?: AbortSignal): Promise<ApiResponse<DataCountDTO>> => {
  const response = await api.get('/api/opinion/data-count', { signal });
  return response.data;
};

export const getSentimentTimeline = async (keyword: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<SentimentTimelineDTO[]>> => {
  const response = await api.get(`/api/opinion/sentiment-timeline?keyword=${encodeURIComponent(keyword)}&timeRange=${timeRange}`, { signal });
  return response.data;
};


export const getSentimentWords = async (keyword: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<Record<string, SentimentWordGroupDTO>>> => {
  const params = new URLSearchParams();
  params.append('keyword', keyword);
  params.append('timeRange', timeRange);
  const response = await api.get(`/api/opinion/sentiment-words?${params.toString()}`, { signal });
  return response.data;
};

export const getAllKeywords = async (signal?: AbortSignal): Promise<ApiResponse<string[]>> => {
  const response = await api.get('/api/opinion/keywords', { signal });
  return response.data;
};

export const getAuthorRanking = async (keyword: string, timeRange: string = '7d', signal?: AbortSignal): Promise<ApiResponse<AuthorDTO[]>> => {
  const response = await api.get('/api/opinion/authors', { params: { keyword, timeRange }, signal });
  return response.data;
};
