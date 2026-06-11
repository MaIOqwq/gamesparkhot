package com.example.opinion_analysis.service;

import com.example.opinion_analysis.model.*;
import com.example.opinion_analysis.repository.StandardizedDataRepository;
import org.ansj.splitWord.analysis.ToAnalysis;
import org.ansj.domain.Term;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

@Service
public class OpinionService {

    private static final Logger log = LoggerFactory.getLogger(OpinionService.class);

    @Autowired
    private StandardizedDataRepository repository;

    @Autowired
    private CacheService cacheService;

    @Autowired
    private RestTemplate restTemplate;

    @Value("${python.service.url:http://localhost:5000/api/predict/trend}")
    private String pythonServiceUrl;

    private static final String DEFAULT_KEYWORD = "手机游戏";
    private static final int TREND_WINDOW_COUNT = 12;

    static {
        ToAnalysis.parse("初始化");
    }
    private static final int MAX_WORD_PROCESS_COUNT = 50;
    private static final int MAX_WORDS_OUTPUT = 120;
    private static final int INFO_LIST_LIMIT = 6;
    private static final double POSITIVE_THRESHOLD = 0.2;
    private static final double NEGATIVE_THRESHOLD = -0.2;

    /** 判断标题是否属于非游戏无关内容（黑名单词匹配） */
    private boolean isIrrelevantContent(String title) {
        if (title == null || title.isEmpty()) return false;
        for (String kw : IRRELEVANT_TOPIC_KEYWORDS) {
            if (title.contains(kw)) return true;
        }
        return false;
    }

    private static final Set<String> STOP_WORDS = Set.of(
        "的", "了", "和", "是", "在", "我", "有", "个", "他", "这", "她", "它",
        "们", "你", "要", "就", "不", "也", "都", "会", "能", "可以", "对", "着",
        "被", "把", "让", "给", "跟", "从", "向", "到", "比", "但", "却", "还",
        "又", "更", "最", "非常", "特别", "这个", "那个", "什么", "怎么", "为什么"
    );

    // 非游戏内容主题词黑名单 — 标题命中则过滤，防止蹭标签的垃圾数据混入
    private static final Set<String> IRRELEVANT_TOPIC_KEYWORDS = Set.of(
        "科普", "知识", "健康", "医疗", "养生", "食谱",
        "美食", "烹饪", "穿搭", "时尚", "化妆", "美妆", "护肤",
        "法律", "财经", "股票", "房产", "理财",
        "育儿", "教育", "考试", "考研", "公务员", "英语", "教辅",
        "健身", "瑜伽", "减肥",
        "恋爱", "情感", "星座", "命理", "风水",
        "装修", "招聘", "求职",
        "摄影", "旅游", "旅行", "探店"
    );

    // 内存缓存：同一 keyword+timeRange 的查询结果在 5 秒内复用，避免并发请求重复查库
    private final ConcurrentHashMap<String, QueryCacheEntry> queryCache = new ConcurrentHashMap<>();
    private static final long QUERY_CACHE_TTL_MS = 5000;

    private static class QueryCacheEntry {
        final List<StandardizedData> data;
        final long expireAt;
        QueryCacheEntry(List<StandardizedData> data) {
            this.data = data;
            this.expireAt = System.currentTimeMillis() + QUERY_CACHE_TTL_MS;
        }
        boolean isValid() { return System.currentTimeMillis() < expireAt; }
    }

    private int parseTimeRange(String timeRange) {
        if (timeRange == null) return 7;
        switch (timeRange) {
            case "1d": return 1;
            case "3d": return 3;
            case "7d": return 7;
            case "1m": return 30;
            case "3m": return 90;
            case "6m": return 180;
            case "1y": return 365;
            case "all": return 36500;
            default:
                try { return Integer.parseInt(timeRange); }
                catch (NumberFormatException e) { return 7; }
        }
    }

    private Date calculateStartTime(String timeRange) {
        int days = parseTimeRange(timeRange);
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.DAY_OF_MONTH, -days);
        return cal.getTime();
    }

    private Date calculatePreviousPeriodStart(String timeRange) {
        int days = parseTimeRange(timeRange);
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.DAY_OF_MONTH, -days * 2);
        return cal.getTime();
    }

    private List<StandardizedData> getDataByKeywordAndRange(String keyword, String timeRange) {
        String cacheKey = keyword + ":" + timeRange;

        // 内存缓存命中 → 直接返回，不走 DB
        QueryCacheEntry entry = queryCache.get(cacheKey);
        if (entry != null && entry.isValid()) {
            return entry.data;
        }

        // 加锁避免并发时重复查库（同一 cacheKey 的请求排队等第一个查完）
        synchronized (cacheKey.intern()) {
            entry = queryCache.get(cacheKey);
            if (entry != null && entry.isValid()) {
                return entry.data;
            }

            Date start = calculateStartTime(timeRange);
            Date end = new Date();
            List<StandardizedData> data;
            if ("全部数据".equals(keyword)) {
                data = repository.findByPublishTimeBetween(start, end);
            } else {
                data = repository.findByKeywordAndPublishTimeBetween(keyword, start, end);
            }

            // 过滤标题命中非游戏内容黑名单的记录（蹭标签垃圾数据）
            if (data != null && !data.isEmpty()) {
                data = data.stream()
                    .filter(d -> !isIrrelevantContent(d.getTitleClean()))
                    .collect(Collectors.toList());
            }

            queryCache.put(cacheKey, new QueryCacheEntry(data));
            return data;
        }
    }

    // --------------------- 核心指标 ---------------------

    public ApiResponse<MetricDTO> getMetricsByKeyword(String keyword, String timeRange) {
        String cacheKey = "metrics:" + keyword + ":" + timeRange;
        ApiResponse<MetricDTO> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) {
            return cached;
        }

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);
        long totalCount = dataList.size();

        // 平均热度
        double avgHotIndex = dataList.stream()
            .mapToDouble(StandardizedData::getHotRaw)
            .average()
            .orElse(0.0);

        // 环比变化：对比上一周期
        double hotIndexChange = computeHotIndexChange(keyword, timeRange, avgHotIndex);

        // 情感占比
        MetricDTO.SentimentRatio ratio = computeSentimentRatio(dataList, totalCount);

        // 平台分布
        long biliCount = dataList.stream().filter(d -> d.getPlatform() == 1).count();
        long ngaCount = dataList.stream().filter(d -> d.getPlatform() == 0).count();
        long socialCount = biliCount;
        long traditionalCount = ngaCount;
        long platformTotal = socialCount + traditionalCount;

        int socialRatio = platformTotal > 0 ? (int) (socialCount * 100 / platformTotal) : 50;
        int traditionalRatio = platformTotal > 0 ? (int) (traditionalCount * 100 / platformTotal) : 50;

        // 迷你趋势数据（取最近7点）
        List<Integer> trendData = computeMiniTrend(dataList);

        MetricDTO metricDTO = new MetricDTO();
        metricDTO.setAverageHotIndex(avgHotIndex);
        metricDTO.setHotIndexChange(hotIndexChange);
        metricDTO.setSentimentRatio(ratio);
        metricDTO.setSocialMediaRatio(socialRatio);
        metricDTO.setTraditionalMediaRatio(traditionalRatio);
        metricDTO.setTrendData(trendData);

        ApiResponse<MetricDTO> result = ApiResponse.success(metricDTO);
        cacheService.set(cacheKey, result);
        return result;
    }

    private double computeHotIndexChange(String keyword, String timeRange, double currentAvg) {
        Date prevStart = calculatePreviousPeriodStart(timeRange);
        Date prevEnd = calculateStartTime(timeRange);
        List<StandardizedData> prevData;
        if ("全部数据".equals(keyword)) {
            prevData = repository.findByPublishTimeBetween(prevStart, prevEnd);
        } else {
            prevData = repository.findByKeywordAndPublishTimeBetween(keyword, prevStart, prevEnd);
        }
        double prevAvg = prevData.stream().mapToDouble(StandardizedData::getHotRaw).average().orElse(0);
        if (prevAvg == 0) return 0;
        return Math.round(((currentAvg - prevAvg) / prevAvg) * 1000.0) / 10.0;
    }

    private MetricDTO.SentimentRatio computeSentimentRatio(List<StandardizedData> dataList, long totalCount) {
        MetricDTO.SentimentRatio ratio = new MetricDTO.SentimentRatio();
        if (totalCount == 0) {
            ratio.setPositive(0);
            ratio.setNeutral(0);
            ratio.setNegative(0);
            return ratio;
        }
        long positive = dataList.stream().filter(d -> d.getSentimentScore() > POSITIVE_THRESHOLD).count();
        long negative = dataList.stream().filter(d -> d.getSentimentScore() < NEGATIVE_THRESHOLD).count();
        long neutral = totalCount - positive - negative;
        ratio.setPositive((int) (positive * 100 / totalCount));
        ratio.setNeutral((int) (neutral * 100 / totalCount));
        ratio.setNegative((int) (negative * 100 / totalCount));
        return ratio;
    }

    private List<Integer> computeMiniTrend(List<StandardizedData> dataList) {
        if (dataList.isEmpty()) return List.of(0);
        Map<Integer, Double> hourly = new TreeMap<>();
        Calendar cal = Calendar.getInstance();
        for (StandardizedData d : dataList) {
            if (d.getPublishTime() == null) continue;
            cal.setTime(d.getPublishTime());
            int slot = cal.get(Calendar.HOUR_OF_DAY) / 4;
            hourly.merge(slot, d.getHotRaw(), Double::sum);
        }
        return hourly.values().stream()
            .map(v -> (int) Math.floor(v))
            .collect(Collectors.toList());
    }

    // --------------------- 渠道分布 ---------------------

    public ApiResponse<List<ChannelDTO>> getChannelDataByKeyword(String keyword, String timeRange) {
        String cacheKey = "channel:" + keyword + ":" + timeRange;
        ApiResponse<List<ChannelDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) {
            return cached;
        }

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);
        long total = dataList.size();

        if (total == 0) {
            ApiResponse<List<ChannelDTO>> empty = ApiResponse.success(List.of());
            cacheService.set(cacheKey, empty);
            return empty;
        }

        long biliCount = dataList.stream().filter(d -> d.getPlatform() == 1).count();
        long ngaCount = dataList.stream().filter(d -> d.getPlatform() == 0).count();

        List<ChannelDTO> result = new ArrayList<>();
        if (biliCount > 0) result.add(new ChannelDTO("B站", (int) (biliCount * 100 / total)));
        if (ngaCount > 0) result.add(new ChannelDTO("NGA", (int) (ngaCount * 100 / total)));

        ApiResponse<List<ChannelDTO>> response = ApiResponse.success(result);
        cacheService.set(cacheKey, response);
        return response;
    }

    // --------------------- 渠道趋势（时间序列） ---------------------

    public ApiResponse<List<ChannelTrendDTO>> getChannelTrendData(String keyword, String timeRange) {
        String cacheKey = "channel_trend:" + keyword + ":" + timeRange;
        ApiResponse<List<ChannelTrendDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) {
            return cached;
        }

        Date endDate = new Date();
        Date startDate = calculateStartTime(timeRange);
        long totalMillis = Math.max(endDate.getTime() - startDate.getTime(), 1);

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);

        Map<Integer, Double> bilibiliSum = new HashMap<>();
        Map<Integer, Double> ngaSum = new HashMap<>();
        for (int i = 0; i < TREND_WINDOW_COUNT; i++) {
            bilibiliSum.put(i, 0.0);
            ngaSum.put(i, 0.0);
        }

        for (StandardizedData data : dataList) {
            if (data.getPublishTime() != null) {
                long elapsed = data.getPublishTime().getTime() - startDate.getTime();
                int idx = Math.min((int) (elapsed * TREND_WINDOW_COUNT / totalMillis), TREND_WINDOW_COUNT - 1);
                if (data.getPlatform() == 1) {
                    bilibiliSum.merge(idx, data.getHotRaw(), Double::sum);
                } else if (data.getPlatform() == 0) {
                    ngaSum.merge(idx, data.getHotRaw(), Double::sum);
                }
            }
        }

        int days = parseTimeRange(timeRange);
        Calendar cal = Calendar.getInstance();
        List<ChannelTrendDTO> result = new ArrayList<>();

        for (int i = 0; i < TREND_WINDOW_COUNT; i++) {
            long mid = startDate.getTime() + totalMillis * i / TREND_WINDOW_COUNT + totalMillis / TREND_WINDOW_COUNT / 2;
            cal.setTime(new Date(mid));
            String label = days <= 7
                ? String.format("%02d/%02d %02d:00", cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH), cal.get(Calendar.HOUR_OF_DAY))
                : String.format("%02d/%02d", cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH));

            double bv = bilibiliSum.get(i);
            double nv = ngaSum.get(i);
            double total = bv + nv;

            ChannelTrendDTO dto = new ChannelTrendDTO();
            dto.setDate(label);
            dto.setBilibiliValue(Math.floor(bv));
            dto.setNgaValue(Math.floor(nv));
            dto.setNgaRatio(total > 0 ? Math.round(nv / total * 10000.0) / 100.0 : 0);
            result.add(dto);
        }

        ApiResponse<List<ChannelTrendDTO>> response = ApiResponse.success(result);
        cacheService.set(cacheKey, response);
        return response;
    }

    public ApiResponse<List<RegionDTO>> getRegionDataByKeyword(String keyword) {
        return ApiResponse.success(List.of());
    }

    // --------------------- 热度趋势 ---------------------

    public ApiResponse<List<TrendDTO>> getTrendDataByKeyword(String keyword, String timeRange) {
        String cacheKey = "trend:" + keyword + ":" + timeRange;
        ApiResponse<List<TrendDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) {
            return cached;
        }

        Date endDate = new Date();
        Date startDate = calculateStartTime(timeRange);

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);

        // "全部" → 用数据实际时间跨度划分12窗口，避免窗口过大导致数据全部挤在最后
        if ("all".equals(timeRange) && !dataList.isEmpty()) {
            Date minPublish = null;
            for (StandardizedData d : dataList) {
                if (d.getPublishTime() != null && (minPublish == null || d.getPublishTime().before(minPublish))) {
                    minPublish = d.getPublishTime();
                }
            }
            if (minPublish != null) startDate = minPublish;
        }

        long totalMillis = Math.max(endDate.getTime() - startDate.getTime(), 1);

        // Group items by window for top content extraction
        Map<Integer, Double> scoreByWindow = new LinkedHashMap<>();
        Map<Integer, List<StandardizedData>> itemsByWindow = new HashMap<>();
        for (int i = 0; i < TREND_WINDOW_COUNT; i++) {
            scoreByWindow.put(i, 0.0);
            itemsByWindow.put(i, new ArrayList<>());
        }

        for (StandardizedData data : dataList) {
            if (data.getPublishTime() != null) {
                long elapsed = data.getPublishTime().getTime() - startDate.getTime();
                int idx = Math.min((int) (elapsed * TREND_WINDOW_COUNT / totalMillis), TREND_WINDOW_COUNT - 1);
                scoreByWindow.merge(idx, data.getHotRaw(), Double::sum);
                itemsByWindow.get(idx).add(data);
            }
        }

        int days = parseTimeRange(timeRange);
        Calendar cal = Calendar.getInstance();
        List<TrendDTO> trendList = new ArrayList<>();

        for (int i = 0; i < TREND_WINDOW_COUNT; i++) {
            long mid = startDate.getTime() + totalMillis * i / TREND_WINDOW_COUNT + totalMillis / TREND_WINDOW_COUNT / 2;
            cal.setTime(new Date(mid));
            String label = days <= 7
                ? String.format("%02d/%02d %02d:00", cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH), cal.get(Calendar.HOUR_OF_DAY))
                : String.format("%02d/%02d", cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH));

            TrendDTO dto = new TrendDTO(label, (int) Math.floor(scoreByWindow.get(i)));

            // Top contents per window
            List<StandardizedData> windowItems = itemsByWindow.get(i);
            if (windowItems != null && !windowItems.isEmpty()) {
                double windowTotal = scoreByWindow.get(i);
                List<TopContentDTO> topContents = windowItems.stream()
                    .sorted((a, b) -> Double.compare(b.getHotRaw(), a.getHotRaw()))
                    .limit(4)
                    .map(item -> {
                        TopContentDTO tc = new TopContentDTO();
                        String title = item.getTitleClean();
                        if (title == null || title.trim().isEmpty()) {
                            String content = item.getContentClean();
                            title = content != null && content.length() > 30
                                ? content.substring(0, 30) + "..."
                                : (content != null ? content : "(无标题)");
                        }
                        tc.setTitle(title);
                        tc.setPlatform(item.getPlatform() == 1 ? "B站" : item.getPlatform() == 0 ? "NGA" : "其他");
                        tc.setHotValue(Math.floor(item.getHotRaw()));
                        tc.setContributionRatio(windowTotal > 0
                            ? Math.round(item.getHotRaw() / windowTotal * 10000.0) / 100.0 : 0);
                        return tc;
                    })
                    .collect(Collectors.toList());
                dto.setTopContents(topContents);
            }

            trendList.add(dto);
        }

        if (!trendList.isEmpty() && List.of("1d", "3d", "7d").contains(timeRange)) {
            TrendDTO last = trendList.get(trendList.size() - 1);
            cal.setTime(new Date());
            cal.add(Calendar.HOUR_OF_DAY, 2);
            String predLabel = String.format("%02d/%02d %02d:00",
                cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH), cal.get(Calendar.HOUR_OF_DAY));

            // 调用 XGBoost 预测服务获取真实预测热度值
            int predValue;
            try {
                Map<String, Object> predResult = predictTrend(keyword);
                Object predHot = predResult.get("predicted_hot");
                if (predHot instanceof Number) {
                    predValue = Math.max((int) Math.floor(((Number) predHot).doubleValue()), 1);
                } else {
                    predValue = Math.max(last.getValue(), 1);
                }
            } catch (Exception e) {
                log.warn("预测服务调用失败，使用当前值兜底: {}", e.getMessage());
                predValue = Math.max(last.getValue(), 1);
            }
            trendList.add(new TrendDTO(predLabel, predValue));
        }

        ApiResponse<List<TrendDTO>> result = ApiResponse.success(trendList);
        cacheService.set(cacheKey, result);
        return result;
    }

    // --------------------- 热词 ---------------------

    public ApiResponse<List<WordDTO>> getWordsDataByKeyword(String keyword, String timeRange) {
        String cacheKey = "words:" + keyword + ":" + timeRange;
        ApiResponse<List<WordDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) {
            return cached;
        }

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);
        if (dataList == null) dataList = List.of();

        // 按 hot_raw 降序排序，取 top200
        List<StandardizedData> topByHot = dataList.stream()
            .sorted((a, b) -> Double.compare(b.getHotRaw(), a.getHotRaw()))
            .limit(200)
            .collect(Collectors.toList());

        // 从 top 数据中提取词，跟踪 freq、sentiment 以及每条词对应的最高热度数据
        Map<String, Integer> freq = new HashMap<>();
        Map<String, Double> sentimentSum = new HashMap<>();
        Map<String, StandardizedData> wordTopItem = new HashMap<>();

        for (StandardizedData data : topByHot) {
            double sent = data.getSentimentScore();
            String text = data.getTitleClean();
            if (text == null || text.trim().isEmpty()) continue;

            try {
                for (Term term : ToAnalysis.parse(text).getTerms()) {
                    String word = term.getName();
                    if (word.length() >= 2 && !STOP_WORDS.contains(word) && !term.getNatureStr().startsWith("w")) {
                        freq.merge(word, 1, Integer::sum);
                        sentimentSum.merge(word, sent, Double::sum);
                        // 记录每个词对应的最高热度数据（首次遇到即最高，因为 topByHot 已按 hot_raw 降序）
                        if (!wordTopItem.containsKey(word)) {
                            wordTopItem.put(word, data);
                        }
                    }
                }
            } catch (Exception e) {
                for (String w : text.replaceAll("[^\\u4e00-\\u9fa5a-zA-Z0-9]", " ").split("\\s+")) {
                    if (w.length() >= 2 && !STOP_WORDS.contains(w) && !wordTopItem.containsKey(w)) {
                        freq.merge(w, 1, Integer::sum);
                        sentimentSum.merge(w, sent, Double::sum);
                        wordTopItem.put(w, data);
                    }
                }
            }
        }

        List<WordDTO> result;
        if (freq.isEmpty()) {
            result = List.of();
        } else {
            int maxFreq = freq.values().stream().max(Integer::compareTo).orElse(1);
            result = freq.entrySet().stream()
                .sorted((a, b) -> b.getValue().compareTo(a.getValue()))
                .limit(MAX_WORDS_OUTPUT)
                .map(e -> {
                    String word = e.getKey();
                    int weight = (int) (e.getValue() * 100.0 / maxFreq);
                    Double avgSent = sentimentSum.containsKey(word)
                        ? Math.round(sentimentSum.get(word) / e.getValue() * 100.0) / 100.0
                        : null;
                    WordDTO dto = new WordDTO(word, weight, avgSent);
                    StandardizedData top = wordTopItem.get(word);
                    if (top != null) {
                        String t = top.getTitleClean();
                        if (t == null || t.trim().isEmpty()) {
                            String c = top.getContentClean();
                            t = c != null && c.length() > 30 ? c.substring(0, 30) + "..." : (c != null ? c : "");
                        }
                        dto.setHotTitle(t);
                        dto.setHotPlatform(top.getPlatform() == 1 ? "B站" : "NGA");
                        dto.setHotValue(Math.floor(top.getHotRaw()));
                    }
                    return dto;
                })
                .collect(Collectors.toList());
        }

        ApiResponse<List<WordDTO>> response = ApiResponse.success(result);
        cacheService.set(cacheKey, response);
        return response;
    }

    private void segmentTextWithSentiment(String text, Map<String, Integer> freq,
                                           Map<String, Double> sentimentSum, double sentiment) {
        if (text == null || text.isEmpty()) return;
        try {
            for (Term term : ToAnalysis.parse(text).getTerms()) {
                String word = term.getName();
                if (word.length() >= 2 && !STOP_WORDS.contains(word) && !term.getNatureStr().startsWith("w")) {
                    freq.merge(word, 1, Integer::sum);
                    sentimentSum.merge(word, sentiment, Double::sum);
                }
            }
        } catch (Exception e) {
            for (String w : text.replaceAll("[^\\u4e00-\\u9fa5a-zA-Z0-9]", " ").split("\\s+")) {
                if (w.length() >= 2 && !STOP_WORDS.contains(w)) {
                    freq.merge(w, 1, Integer::sum);
                    sentimentSum.merge(w, sentiment, Double::sum);
                }
            }
        }
    }

    private void segmentText(String text, Map<String, Integer> freq) {
        if (text == null || text.isEmpty()) return;
        try {
            for (Term term : ToAnalysis.parse(text).getTerms()) {
                String word = term.getName();
                if (word.length() >= 2 && !STOP_WORDS.contains(word) && !term.getNatureStr().startsWith("w")) {
                    freq.merge(word, 1, Integer::sum);
                }
            }
        } catch (Exception e) {
            for (String w : text.replaceAll("[^\\u4e00-\\u9fa5a-zA-Z0-9]", " ").split("\\s+")) {
                if (w.length() >= 2 && !STOP_WORDS.contains(w)) {
                    freq.merge(w, 1, Integer::sum);
                }
            }
        }
    }

    // --------------------- 情绪焦点词 ---------------------

    public ApiResponse<Map<String, SentimentWordGroupDTO>> getSentimentWordsByKeyword(String keyword, String timeRange) {
        String cacheKey = "sentiment_words:" + keyword + ":" + timeRange;
        ApiResponse<Map<String, SentimentWordGroupDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) return cached;

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);
        if (dataList == null || dataList.isEmpty()) {
            ApiResponse<Map<String, SentimentWordGroupDTO>> empty = ApiResponse.success(Map.of());
            cacheService.set(cacheKey, empty);
            return empty;
        }

        // 按情感分组
        List<StandardizedData> positiveGroup = new ArrayList<>();
        List<StandardizedData> neutralGroup = new ArrayList<>();
        List<StandardizedData> negativeGroup = new ArrayList<>();

        for (StandardizedData d : dataList) {
            double score = d.getSentimentScore();
            if (score > POSITIVE_THRESHOLD) positiveGroup.add(d);
            else if (score < NEGATIVE_THRESHOLD) negativeGroup.add(d);
            else neutralGroup.add(d);
        }

        Map<String, SentimentWordGroupDTO> result = new LinkedHashMap<>();
        result.put("positive", buildSentimentWordGroup(positiveGroup, "positive", "正面"));
        result.put("neutral", buildSentimentWordGroup(neutralGroup, "neutral", "中性"));
        result.put("negative", buildSentimentWordGroup(negativeGroup, "negative", "负面"));

        ApiResponse<Map<String, SentimentWordGroupDTO>> response = ApiResponse.success(result);
        cacheService.set(cacheKey, response);
        return response;
    }

    private SentimentWordGroupDTO buildSentimentWordGroup(List<StandardizedData> dataList, String sentiment, String label) {
        if (dataList == null || dataList.isEmpty()) {
            return new SentimentWordGroupDTO(sentiment, label, List.of());
        }

        // 取 top 100 按热度排序的数据提取词
        List<StandardizedData> topByHot = dataList.stream()
            .sorted((a, b) -> Double.compare(b.getHotRaw(), a.getHotRaw()))
            .limit(100)
            .collect(Collectors.toList());

        Map<String, Integer> freq = new HashMap<>();
        for (StandardizedData data : topByHot) {
            String text = data.getTitleClean();
            if (text == null || text.trim().isEmpty()) continue;
            segmentText(text, freq);
        }

        if (freq.isEmpty()) {
            return new SentimentWordGroupDTO(sentiment, label, List.of());
        }

        int maxFreq = freq.values().stream().max(Integer::compareTo).orElse(1);
        List<SentimentWordItemDTO> words = freq.entrySet().stream()
            .sorted((a, b) -> b.getValue().compareTo(a.getValue()))
            .limit(30)
            .map(e -> new SentimentWordItemDTO(e.getKey(),
                (int) (e.getValue() * 100.0 / maxFreq), e.getValue()))
            .collect(Collectors.toList());

        return new SentimentWordGroupDTO(sentiment, label, words);
    }

    // --------------------- 信息流列表 ---------------------

    public ApiResponse<List<InfoItemDTO>> getInfoListByKeyword(String keyword, String timeRange) {
        String cacheKey = "list:" + keyword + ":" + timeRange;
        ApiResponse<List<InfoItemDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) {
            return cached;
        }

        Date endDate = new Date();
        Date startDate = calculateStartTime(timeRange);
        List<StandardizedData> dataList;
        if ("全部数据".equals(keyword)) {
            dataList = repository.findTop100ByTimeRangeOrderByHotRaw(startDate, endDate);
        } else {
            dataList = repository.findTop100ByKeywordAndTimeRangeOrderByHotRaw(keyword, startDate, endDate);
        }
        List<InfoItemDTO> result = buildInfoList(dataList);

        ApiResponse<List<InfoItemDTO>> response = ApiResponse.success(result);
        cacheService.set(cacheKey, response);
        return response;
    }

    private List<InfoItemDTO> buildInfoList(List<StandardizedData> dataList) {
        if (dataList.isEmpty()) return List.of();
        Date now = new Date();
        List<InfoItemDTO> items = dataList.stream()
            .sorted((a, b) -> {
                int c = Double.compare(b.getHotScore(), a.getHotScore());
                return c != 0 ? c : b.getPublishTime().compareTo(a.getPublishTime());
            })
            .limit(INFO_LIST_LIMIT)
            .map(data -> {
                String title = data.getTitleClean();
                if (title == null || title.trim().isEmpty()) {
                    String content = data.getContentClean();
                    title = content != null && content.length() > 50
                        ? content.substring(0, 50) + "..."
                        : (content != null ? content : "无标题");
                }
                long hours = (now.getTime() - data.getPublishTime().getTime()) / (1000 * 60 * 60);
                String timeLabel = hours < 1 ? "刚刚" : hours < 24 ? hours + "小时前" : hours / 24 + "天前";
                String sentiment = data.getSentimentScore() > POSITIVE_THRESHOLD ? "positive"
                    : data.getSentimentScore() < NEGATIVE_THRESHOLD ? "negative" : "neutral";
                String source;
                if (data.getPlatform() == 1) source = "B站";
                else if (data.getPlatform() == 0) source = "NGA";
                else source = "其他";
                return new InfoItemDTO(source, title, timeLabel, sentiment, (int) Math.floor(data.getHotRaw()));
            })
            .collect(Collectors.toList());

        for (int i = 0; i < items.size(); i++) {
            items.get(i).setId(i + 1);
        }

        // 计算每项的 hotChange 和趋势方向
        double avgHot = items.stream().mapToInt(InfoItemDTO::getHotValue).average().orElse(0);
        for (InfoItemDTO item : items) {
            int diff = (int) (item.getHotValue() - avgHot);
            double pct = avgHot > 0 ? diff / avgHot * 100 : 0;
            item.setHotChange(diff);
            item.setHotChangePercent(Math.round(pct * 100.0) / 100.0);
            if (pct > 5) item.setTrend("up");
            else if (pct < -5) item.setTrend("down");
            else item.setTrend("stable");
        }

        return items;
    }

    // --------------------- 预测（规则型：均值回归） ---------------------

    /**
     * 基于均值回归的规则型预测：
     * 将近期数据分成 N 个窗口，比较最新窗口与历史均值的偏差。
     * 逻辑：当前窗口显著高于历史均值 → 预测下跌（均值回归）
     *       当前窗口显著低于历史均值 → 预测上涨（均值回归）
     *       否则 → 平稳
     */
    private static final double UP_DEVIATION_THRESHOLD = 0.25;   // 高于均值 25% 预测跌
    private static final double DOWN_DEVIATION_THRESHOLD = -0.20; // 低于均值 20% 预测涨

    public Map<String, Object> predictTrend(String keyword) {
        try {
            String urlStr = pythonServiceUrl + "?keyword=" + URLEncoder.encode(keyword, StandardCharsets.UTF_8.name());
            java.net.URI uri = new java.net.URI(urlStr);
            String json = restTemplate.getForObject(uri, String.class);
            if (json != null) {
                com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                Map<String, Object> response = mapper.readValue(json, Map.class);
                Object code = response.get("code");
                if (code instanceof Number && ((Number) code).intValue() == 200) {
                    Map<String, Object> data = (Map<String, Object>) response.get("data");
                    if (data != null) {
                        // 对 change_rate 做合理性截断：超出 ±10（±1000%）的不合理值截掉
                        Object cr = data.get("change_rate");
                        if (cr instanceof Number) {
                            double v = ((Number) cr).doubleValue();
                            if (v > 10) data.put("change_rate", 10.0);
                            else if (v < -10) data.put("change_rate", -10.0);
                        }
                        log.info("ML预测成功: keyword={}, trend={}", keyword, data.get("trend_label"));
                        return data;
                    }
                }
            }
        } catch (Exception e) {
            log.warn("ML服务预测失败(降级到规则预测): {}", e.getMessage());
        }
        try {
            Map<String, Object> result = computeDayOverDayPrediction(keyword);
            if (result != null) return result;
        } catch (Exception e) {
            log.warn("规则预测失败: {}", e.getMessage());
        }
        return defaultPrediction(keyword);
    }

    /**
     * 同日同比均值回归预测：
     * 将最近数据按天+时间段分组，今天同时间段 vs 昨天同时间段比较。
     * 控制日内周期影响（如白天 vs 深夜），同时利用均值回归特性。
     */
    private static final int DOD_SLOTS = 6; // 每天分成 6 个 4h 时段

    private Map<String, Object> computeDayOverDayPrediction(String keyword) {
        Date now = new Date();
        Calendar cal = Calendar.getInstance();

        // 查询最近 3 天数据
        cal.setTime(now);
        cal.add(Calendar.DAY_OF_MONTH, -3);
        Date start = cal.getTime();

        List<StandardizedData> dataList = repository.findByKeywordAndPublishTimeBetween(keyword, start, now);
        if (dataList == null || dataList.size() < 20) return null;

        // 按 4h slot 汇总：key = "yyyyMMdd_HH" (HH = 0/4/8/12/16/20)
        Map<String, List<Double>> slotData = new LinkedHashMap<>();
        for (StandardizedData d : dataList) {
            if (d.getPublishTime() == null) continue;
            cal.setTime(d.getPublishTime());
            int hourSlot = (cal.get(Calendar.HOUR_OF_DAY) / 4) * 4;
            String key = String.format("%04d%02d%02d_%02d",
                cal.get(Calendar.YEAR), cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH), hourSlot);
            slotData.computeIfAbsent(key, k -> new ArrayList<>()).add(d.getHotRaw());
        }

        if (slotData.size() < 2) return null;

        // 找到今天最新有数据的 slot，与昨天同 slot 比较
        List<String> sortedSlots = new ArrayList<>(slotData.keySet());
        Collections.sort(sortedSlots);
        String latestSlot = sortedSlots.get(sortedSlots.size() - 1);

        // 解析最新 slot 的日期和 hour
        String latestDatePart = latestSlot.substring(0, 8); // yyyyMMdd
        int latestHour = Integer.parseInt(latestSlot.substring(9)); // 0/4/8/12/16/20

        // 计算昨天的同日期
        cal.set(Integer.parseInt(latestDatePart.substring(0, 4)),
                Integer.parseInt(latestDatePart.substring(4, 6)) - 1,
                Integer.parseInt(latestDatePart.substring(6, 8)));
        cal.add(Calendar.DAY_OF_MONTH, -1);
        String yesterdaySlot = String.format("%04d%02d%02d_%02d",
            cal.get(Calendar.YEAR), cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH), latestHour);

        // 获取今天和昨天的数据
        List<Double> todayData = slotData.get(latestSlot);
        List<Double> yesterdayData = slotData.get(yesterdaySlot);

        double currentAvg = todayData.stream().mapToDouble(Double::doubleValue).average().orElse(0);
        double yesterdayAvg = (yesterdayData != null && !yesterdayData.isEmpty())
            ? yesterdayData.stream().mapToDouble(Double::doubleValue).average().orElse(0)
            : 0;

        // 如果昨天没有同 slot 数据，回退到其他历史 slot 的均值
        if (yesterdayAvg == 0) {
            double sum = 0;
            int cnt = 0;
            for (int i = 0; i < sortedSlots.size() - 1; i++) {
                List<Double> vals = slotData.get(sortedSlots.get(i));
                for (double v : vals) {
                    sum += v;
                    cnt++;
                }
            }
            yesterdayAvg = cnt > 0 ? sum / cnt : currentAvg;
        }

        if (yesterdayAvg == 0) return null;

        // 偏差 = (今天 - 昨天) / 昨天
        double deviation = (currentAvg - yesterdayAvg) / yesterdayAvg;

        // 判断
        int trendCode;
        String trendLabel;
        double confidence = 0.5 + Math.min(Math.abs(deviation), 1.0) * 0.45;

        if (deviation > UP_DEVIATION_THRESHOLD) {
            // 今天显著高于昨天 → 均值回归预测跌
            trendCode = 1;
            trendLabel = "跌";
        } else if (deviation < DOWN_DEVIATION_THRESHOLD) {
            // 今天显著低于昨天 → 均值回归预测涨
            trendCode = 3;
            trendLabel = "涨";
        } else {
            trendCode = 2;
            trendLabel = "平稳";
            confidence = 0.6;
        }

        // 计算热度值（基于当天数据推算）
        double currentHot = currentAvg * todayData.size();
        double predictedHot = currentAvg * todayData.size();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("keyword", keyword);
        result.put("trend_code", trendCode);
        result.put("trend_label", trendLabel);
        result.put("confidence", Math.round(confidence * 100.0) / 100.0);
        result.put("predicted_hot", Math.floor(predictedHot));
        result.put("current_hot", Math.floor(currentHot));
        result.put("change_rate", Math.round(deviation * 1000.0) / 1000.0);
        result.put("strategy", "同日同比·均值回归");
        String msg = trendLabel.equals("涨") ? "回升" :
                     trendLabel.equals("跌") ? "回落" : "维持";
        String rateStr = String.format("%+.0f%%", deviation * 100);
        result.put("message", String.format("同日同比，预测%s（当前%s，置信度%.0f%%）", msg, rateStr, confidence * 100));
        return result;
    }

    private Map<String, Object> defaultPrediction(String keyword) {
        Map<String, Object> fallback = new LinkedHashMap<>();
        fallback.put("keyword", keyword);
        fallback.put("trend_code", 2);
        fallback.put("trend_label", "平稳");
        fallback.put("confidence", 0.5);
        fallback.put("predicted_hot", 0);
        fallback.put("current_hot", 0);
        fallback.put("change_rate", 0);
        fallback.put("strategy", "默认");
        fallback.put("message", "数据不足，默认平稳");
        return fallback;
    }

    // --------------------- 预警面板 ---------------------

    public ApiResponse<List<WarningDTO>> getWarnings(String timeRange) {
        String cacheKey = "warnings:" + timeRange;
        ApiResponse<List<WarningDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) return cached;

        Date start = calculateStartTime(timeRange);
        Date now = new Date();
        long totalMillis = Math.max(now.getTime() - start.getTime(), 1);
        int WINDOWS = 12;

        List<WarningDTO> warnings = new ArrayList<>();

        // 一次查询全部数据，按 keyword 分组 — 消除 N+1
        List<StandardizedData> allData = repository.findByPublishTimeBetween(start, now);
        if (allData == null || allData.isEmpty()) {
            ApiResponse<List<WarningDTO>> result = ApiResponse.success(warnings);
            cacheService.set(cacheKey, result);
            return result;
        }

        Map<String, List<StandardizedData>> dataByKeyword = allData.stream()
            .filter(d -> d.getKeyword() != null && !d.getKeyword().isEmpty())
            .collect(Collectors.groupingBy(StandardizedData::getKeyword));

        for (Map.Entry<String, List<StandardizedData>> entry : dataByKeyword.entrySet()) {
            String keyword = entry.getKey();
            List<StandardizedData> dataList = entry.getValue();

            // 12个等宽时间窗口，聚合热度值（总和）
            double[] windowSums = new double[WINDOWS];
            for (StandardizedData d : dataList) {
                if (d.getPublishTime() == null) continue;
                long elapsed = d.getPublishTime().getTime() - start.getTime();
                int idx = Math.min((int) (elapsed * WINDOWS / totalMillis), WINDOWS - 1);
                windowSums[idx] += d.getHotRaw();
            }

            // 相邻窗口变化率（共 11 个）
            double[] changeRates = new double[WINDOWS - 1];
            for (int i = 0; i < WINDOWS - 1; i++) {
                changeRates[i] = windowSums[i] > 0
                    ? (windowSums[i + 1] - windowSums[i]) / windowSums[i]
                    : 0;
            }

            double currentChangeRate = changeRates[WINDOWS - 2]; // 窗口12 vs 窗口11
            double currentSum = windowSums[WINDOWS - 1];

            // 动态阈值：前 10 个 changeRate 计算 μ 和 σ
            double mu = 0, sigma = 0;
            int histCount = WINDOWS - 2;
            for (int i = 0; i < histCount; i++) mu += changeRates[i];
            mu /= histCount;
            double sumSq = 0;
            for (int i = 0; i < histCount; i++) sumSq += (changeRates[i] - mu) * (changeRates[i] - mu);
            sigma = Math.sqrt(sumSq / histCount);

            String level, message, trend;
            int trendCode;

            if (sigma > 0.01) {
                double dev = (currentChangeRate - mu) / sigma;
                if (dev > 1.5 && currentSum > 0.5) {
                    level = "danger";  trend = "增长";  trendCode = 4;
                    message = String.format("热度增长(偏离%.1fσ)，建议重点关注", dev);
                } else if (dev < -1.5 && currentSum < 0.3) {
                    level = "danger";  trend = "下降";  trendCode = 0;
                    message = String.format("热度下降(偏离%.1fσ)，内容活力不足", Math.abs(dev));
                } else if (dev > 1.0) {
                    level = "warning";  trend = "增长";  trendCode = 3;
                    message = String.format("热度增长(偏离%.1fσ)，趋势向好", dev);
                } else if (dev < -1.0) {
                    level = "warning";  trend = "下降";  trendCode = 1;
                    message = String.format("热度下降(偏离%.1fσ)，需关注", Math.abs(dev));
                } else {
                    level = "normal";  trend = "平稳";  trendCode = 2;
                    message = "趋势平稳";
                }
            } else {
                // sigma 太小 → 固定阈值兜底
                if (currentChangeRate > 1.0 && currentSum > 0.5) {
                    level = "danger";  trend = "增长";  trendCode = 4;
                    message = String.format("热度增长 %.0f%%，建议重点关注", currentChangeRate * 100);
                } else if (currentChangeRate < -0.5 && currentSum < 0.3) {
                    level = "danger";  trend = "下降";  trendCode = 0;
                    message = String.format("热度下降 %.0f%%，内容活力不足", Math.abs(currentChangeRate) * 100);
                } else if (currentChangeRate > 0.5) {
                    level = "warning";  trend = "增长";  trendCode = 3;
                    message = String.format("热度增长 %.0f%%，趋势向好", currentChangeRate * 100);
                } else if (currentChangeRate < -0.3) {
                    level = "warning";  trend = "下降";  trendCode = 1;
                    message = String.format("热度下降 %.0f%%，需关注", Math.abs(currentChangeRate) * 100);
                } else {
                    level = "normal";  trend = "平稳";  trendCode = 2;
                    message = "趋势平稳";
                }
            }

            // 情感辅助判定
            double currentSentiment = dataList.stream()
                .mapToDouble(StandardizedData::getSentimentScore)
                .average().orElse(0);
            if (currentSentiment > 0.5) {
                message += " · 舆论正面";
            } else if (currentSentiment < -0.3) {
                message += " · 舆论负面";
                if (!"danger".equals(level)) level = "warning";
            }

            warnings.add(new WarningDTO(keyword, currentSum, currentChangeRate, trend, trendCode, 0, level, message));
        }

        // 按 severity 排序：danger 优先，然后按 |changeRate| 降序
        warnings.sort((a, b) -> {
            int severityCmp = severity(a.getLevel()) - severity(b.getLevel());
            if (severityCmp != 0) return severityCmp;
            return Double.compare(Math.abs(b.getChangeRate()), Math.abs(a.getChangeRate()));
        });

        ApiResponse<List<WarningDTO>> result = ApiResponse.success(warnings);
        cacheService.set(cacheKey, result);
        return result;
    }

    private int severity(String level) {
        switch (level) {
            case "danger": return 0;
            case "warning": return 1;
            default: return 2;
        }
    }

    // --------------------- 实时数据计数 ---------------------

    public ApiResponse<Map<String, Object>> getDataCount() {
        Calendar cal = Calendar.getInstance();

        // 过去12小时的2小时窗口
        Date twelveHoursAgo = new Date(System.currentTimeMillis() - 12 * 60 * 60 * 1000L);

        cal.set(Calendar.HOUR_OF_DAY, 0);
        cal.set(Calendar.MINUTE, 0);
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        Date todayStart = cal.getTime();

        Date last24h = new Date(System.currentTimeMillis() - 24 * 60 * 60 * 1000L);

        long todayCount = repository.countByPublishTimeAfter(todayStart);
        long last24hCount = repository.countByPublishTimeAfter(last24h);
        long totalCount = repository.count();
        Date lastUpdate = repository.findLastPublishTime();

        // 按2小时窗口统计过去12小时的数据
        List<Object[]> hourlyRows = repository.countByHourSince(twelveHoursAgo);
        Map<Integer, Integer> hourlyMap = new HashMap<>();
        for (Object[] row : hourlyRows) {
            hourlyMap.put(((Number) row[0]).intValue(), ((Number) row[1]).intValue());
        }
        List<Map<String, Object>> hourlyData = new ArrayList<>();
        // 生成过去12小时的2小时窗口（从 twelveHoursAgo 的整点开始）
        cal.setTime(twelveHoursAgo);
        int startH = (cal.get(Calendar.HOUR_OF_DAY) / 2) * 2;
        for (int h = startH; ; h += 2) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("hour", String.format("%02d", h % 24));
            item.put("count", hourlyMap.getOrDefault(h % 24, 0));
            hourlyData.add(item);
            if (h - startH >= 10) break; // 12小时 = 6个窗口，从startH到startH+10
        }

        // 最新5条
        List<Object[]> latestRows = repository.findLatestTop5();
        List<Map<String, Object>> latestEntries = new ArrayList<>();
        java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("MM/dd HH:mm");
        for (Object[] row : latestRows) {
            Map<String, Object> item = new LinkedHashMap<>();
            String title = row[0] != null ? row[0].toString() : null;
            if (title == null || title.trim().isEmpty()) {
                String content = row[1] != null ? row[1].toString() : null;
                title = content != null && content.length() > 30
                    ? content.substring(0, 30) + "..."
                    : (content != null ? content : "(无标题)");
            }
            item.put("title", title);
            int platform = row[2] != null ? ((Number) row[2]).intValue() : 0;
            item.put("platform", platform == 1 ? "B站" : "NGA");
            item.put("hotValue", row[3] != null ? ((Number) row[3]).doubleValue() : 0);
            item.put("publishTime", row[4] != null ? sdf.format(row[4]) : "");
            latestEntries.add(item);
        }

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("todayCount", todayCount);
        data.put("last24hCount", last24hCount);
        data.put("totalCount", totalCount);
        data.put("lastUpdateTime", lastUpdate);
        data.put("hourlyData", hourlyData);
        data.put("latestEntries", latestEntries);

        return ApiResponse.success(data);
    }

    // --------------------- 情感时间线 ---------------------

    public ApiResponse<List<SentimentTimelineDTO>> getSentimentTimeline(String keyword, String timeRange) {
        String cacheKey = "sentiment_timeline:" + keyword + ":" + timeRange;
        ApiResponse<List<SentimentTimelineDTO>> cached = cacheService.get(cacheKey, ApiResponse.class);
        if (cached != null) return cached;

        Date endDate = new Date();
        Date startDate = calculateStartTime(timeRange);
        long totalMillis = Math.max(endDate.getTime() - startDate.getTime(), 1);

        List<StandardizedData> dataList = getDataByKeywordAndRange(keyword, timeRange);

        // 12 个时间窗口
        int WINDOWS = 12;
        int[] positive = new int[WINDOWS];
        int[] neutral = new int[WINDOWS];
        int[] negative = new int[WINDOWS];
        int[] counts = new int[WINDOWS];

        for (StandardizedData data : dataList) {
            if (data.getPublishTime() != null) {
                long elapsed = data.getPublishTime().getTime() - startDate.getTime();
                int idx = Math.min((int) (elapsed * WINDOWS / totalMillis), WINDOWS - 1);
                counts[idx]++;

                double score = data.getSentimentScore();
                if (score > POSITIVE_THRESHOLD) positive[idx]++;
                else if (score < NEGATIVE_THRESHOLD) negative[idx]++;
                else neutral[idx]++;
            }
        }

        List<SentimentTimelineDTO> timeline = new ArrayList<>();
        int days = parseTimeRange(timeRange);
        Calendar cal = Calendar.getInstance();

        for (int i = 0; i < WINDOWS; i++) {
            long mid = startDate.getTime() + totalMillis * i / WINDOWS + totalMillis / WINDOWS / 2;
            cal.setTime(new Date(mid));
            String label = days <= 7
                ? String.format("%02d/%02d %02d:00", cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH), cal.get(Calendar.HOUR_OF_DAY))
                : String.format("%02d/%02d", cal.get(Calendar.MONTH) + 1, cal.get(Calendar.DAY_OF_MONTH));
            timeline.add(new SentimentTimelineDTO(label, positive[i], neutral[i], negative[i]));
        }

        ApiResponse<List<SentimentTimelineDTO>> result = ApiResponse.success(timeline);
        cacheService.set(cacheKey, result);
        return result;
    }

    // --------------------- 作者排行 ---------------------

    public ApiResponse<List<AuthorDTO>> getAuthorRanking(String keyword, String timeRange) {
        List<Object[]> rows;
        if ("all".equals(timeRange)) {
            rows = repository.findAuthorRankingByKeyword(keyword);
        } else {
            Date endDate = new Date();
            Date startDate = calculateStartTime(timeRange);
            rows = repository.findAuthorRankingByKeywordAndTimeRange(keyword, startDate, endDate);
        }
        List<AuthorDTO> result = new ArrayList<>();
        for (Object[] row : rows) {
            result.add(new AuthorDTO(
                (String) row[0],
                ((Number) row[1]).intValue(),
                ((Number) row[2]).doubleValue(),
                ((Number) row[3]).doubleValue()
            ));
        }
        return ApiResponse.success(result);
    }

    // --------------------- 全量关键词 ---------------------

    public ApiResponse<List<String>> getAllKeywords() {
        List<String> keywords = repository.findDistinctKeywords();
        return ApiResponse.success(keywords);
    }
}
