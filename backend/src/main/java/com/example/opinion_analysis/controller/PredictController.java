package com.example.opinion_analysis.controller;

import com.example.opinion_analysis.model.ApiResponse;
import com.example.opinion_analysis.service.OpinionService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/predict")
public class PredictController {

    @Autowired
    private OpinionService opinionService;

    @GetMapping("/trend")
    public ApiResponse<Map<String, Object>> predictTrend(@RequestParam String keyword) {
        try {
            Map<String, Object> result = opinionService.predictTrend(keyword);
            return ApiResponse.success(result);
        } catch (Exception e) {
            return ApiResponse.error(500, "预测失败: " + e.getMessage());
        }
    }

    @PostMapping("/trend/batch")
    public ApiResponse<List<Map<String, Object>>> predictTrendBatch(@RequestBody Map<String, Object> request) {
        try {
            @SuppressWarnings("unchecked")
            List<String> keywords = (List<String>) request.get("keywords");

            List<Map<String, Object>> results = new ArrayList<>();
            for (String keyword : keywords) {
                results.add(opinionService.predictTrend(keyword));
            }

            return ApiResponse.success(results);
        } catch (Exception e) {
            return ApiResponse.error(500, "批量预测失败: " + e.getMessage());
        }
    }
}
