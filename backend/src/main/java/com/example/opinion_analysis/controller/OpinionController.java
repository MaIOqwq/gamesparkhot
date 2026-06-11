package com.example.opinion_analysis.controller;

import com.example.opinion_analysis.model.*;
import com.example.opinion_analysis.service.OpinionService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/opinion")
public class OpinionController {

    @Autowired
    private OpinionService opinionService;

    @GetMapping("/health")
    public ApiResponse<String> health() {
        return ApiResponse.success("Opinion Analysis API is running");
    }

    @GetMapping("/metrics")
    public ApiResponse<MetricDTO> getMetrics(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getMetricsByKeyword(keyword, timeRange);
    }

    @GetMapping("/channel")
    public ApiResponse<List<ChannelDTO>> getChannelData(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getChannelDataByKeyword(keyword, timeRange);
    }

    @GetMapping("/channel-trend")
    public ApiResponse<List<ChannelTrendDTO>> getChannelTrend(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getChannelTrendData(keyword, timeRange);
    }

    @GetMapping("/region")
    public ApiResponse<List<RegionDTO>> getRegionData(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword) {
        return opinionService.getRegionDataByKeyword(keyword);
    }

    @GetMapping("/trend")
    public ApiResponse<List<TrendDTO>> getTrendData(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getTrendDataByKeyword(keyword, timeRange);
    }

    @GetMapping("/words")
    public ApiResponse<List<WordDTO>> getWordsData(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getWordsDataByKeyword(keyword, timeRange);
    }

    @GetMapping("/list")
    public ApiResponse<List<InfoItemDTO>> getInfoList(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getInfoListByKeyword(keyword, timeRange);
    }

    @GetMapping("/warnings")
    public ApiResponse<List<WarningDTO>> getWarnings(
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getWarnings(timeRange);
    }

    @GetMapping("/data-count")
    public ApiResponse<Map<String, Object>> getDataCount() {
        return opinionService.getDataCount();
    }

    @GetMapping("/sentiment-timeline")
    public ApiResponse<List<SentimentTimelineDTO>> getSentimentTimeline(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getSentimentTimeline(keyword, timeRange);
    }

    @GetMapping("/sentiment-words")
    public ApiResponse<Map<String, SentimentWordGroupDTO>> getSentimentWords(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getSentimentWordsByKeyword(keyword, timeRange);
    }

    @GetMapping("/keywords")
    public ApiResponse<List<String>> getAllKeywords() {
        return opinionService.getAllKeywords();
    }

    @GetMapping("/authors")
    public ApiResponse<List<AuthorDTO>> getAuthorRanking(
            @RequestParam(value = "keyword", defaultValue = "手机游戏") String keyword,
            @RequestParam(value = "timeRange", defaultValue = "7d") String timeRange) {
        return opinionService.getAuthorRanking(keyword, timeRange);
    }
}
