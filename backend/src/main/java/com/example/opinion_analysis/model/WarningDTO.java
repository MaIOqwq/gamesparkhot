package com.example.opinion_analysis.model;

public class WarningDTO {
    private String keyword;
    private double currentHot;
    private double changeRate;
    private String trend;
    private int trendCode;
    private double confidence;
    private String level;   // "danger", "warning", "normal"
    private String message;

    public WarningDTO() {}

    public WarningDTO(String keyword, double currentHot, double changeRate,
                      String trend, int trendCode, double confidence,
                      String level, String message) {
        this.keyword = keyword;
        this.currentHot = currentHot;
        this.changeRate = changeRate;
        this.trend = trend;
        this.trendCode = trendCode;
        this.confidence = confidence;
        this.level = level;
        this.message = message;
    }

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) { this.keyword = keyword; }
    public double getCurrentHot() { return currentHot; }
    public void setCurrentHot(double currentHot) { this.currentHot = currentHot; }
    public double getChangeRate() { return changeRate; }
    public void setChangeRate(double changeRate) { this.changeRate = changeRate; }
    public String getTrend() { return trend; }
    public void setTrend(String trend) { this.trend = trend; }
    public int getTrendCode() { return trendCode; }
    public void setTrendCode(int trendCode) { this.trendCode = trendCode; }
    public double getConfidence() { return confidence; }
    public void setConfidence(double confidence) { this.confidence = confidence; }
    public String getLevel() { return level; }
    public void setLevel(String level) { this.level = level; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
}
