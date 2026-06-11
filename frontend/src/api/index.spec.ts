import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getMetrics,
  getChannelData,
  getTrendData,
  getWordsData,
  getInfoList,
} from './index';

const mockGet = vi.hoisted(() => vi.fn());
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
    })),
  },
}));

describe('API Functions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getMetrics', () => {
    it('should make GET request with keyword and timeRange as query parameters', async () => {
      const mockResponse = {
        data: { code: 200, message: 'success', data: {} }
      };
      mockGet.mockResolvedValue(mockResponse);

      await getMetrics('王者荣耀', '7d');

      expect(mockGet).toHaveBeenCalledWith('/api/opinion/metrics?keyword=' + encodeURIComponent('王者荣耀') + '&timeRange=7d');
    });

    it('should handle request without keyword', async () => {
      const mockResponse = {
        data: { code: 200, message: 'success', data: {} }
      };
      mockGet.mockResolvedValue(mockResponse);

      await getMetrics(undefined, '7d');

      expect(mockGet).toHaveBeenCalledWith('/api/opinion/metrics?timeRange=7d');
    });

    it('should throw on network error', async () => {
      mockGet.mockRejectedValue(new Error('Network error'));

      await expect(getMetrics('王者荣耀', '7d')).rejects.toThrow('Network error');
    });
  });

  describe('getChannelData', () => {
    it('should make GET request with correct parameters', async () => {
      const mockResponse = {
        data: { code: 200, message: 'success', data: [] }
      };
      mockGet.mockResolvedValue(mockResponse);

      await getChannelData('王者荣耀', '7d');

      expect(mockGet).toHaveBeenCalledWith('/api/opinion/channel?keyword=' + encodeURIComponent('王者荣耀') + '&timeRange=7d');
    });
  });

  describe('getTrendData', () => {
    it('should make GET request with correct parameters', async () => {
      const mockResponse = {
        data: { code: 200, message: 'success', data: [] }
      };
      mockGet.mockResolvedValue(mockResponse);

      await getTrendData('王者荣耀', '7d');

      expect(mockGet).toHaveBeenCalledWith('/api/opinion/trend?keyword=' + encodeURIComponent('王者荣耀') + '&timeRange=7d');
    });
  });

  describe('getWordsData', () => {
    it('should make GET request with correct parameters', async () => {
      const mockResponse = {
        data: { code: 200, message: 'success', data: [] }
      };
      mockGet.mockResolvedValue(mockResponse);

      await getWordsData('王者荣耀', '7d');

      expect(mockGet).toHaveBeenCalledWith('/api/opinion/words?keyword=' + encodeURIComponent('王者荣耀') + '&timeRange=7d');
    });
  });

  describe('getInfoList', () => {
    it('should make GET request with correct parameters', async () => {
      const mockResponse = {
        data: { code: 200, message: 'success', data: [] }
      };
      mockGet.mockResolvedValue(mockResponse);

      await getInfoList('王者荣耀', '7d');

      expect(mockGet).toHaveBeenCalledWith('/api/opinion/list?keyword=' + encodeURIComponent('王者荣耀') + '&timeRange=7d');
    });
  });
});
