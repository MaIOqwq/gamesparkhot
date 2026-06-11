package com.example.opinion_analysis.model;

import java.util.List;

public class MetricDTO {
    private double averageHotIndex;
    private double hotIndexChange;
    private SentimentRatio sentimentRatio;
    private int socialMediaRatio;
    private int traditionalMediaRatio;
    private List<Integer> trendData;

    public double getAverageHotIndex() {
        return averageHotIndex;
    }

    public void setAverageHotIndex(double averageHotIndex) {
        this.averageHotIndex = averageHotIndex;
    }

    public double getHotIndexChange() {
        return hotIndexChange;
    }

    public void setHotIndexChange(double hotIndexChange) {
        this.hotIndexChange = hotIndexChange;
    }

    public SentimentRatio getSentimentRatio() {
        return sentimentRatio;
    }

    public void setSentimentRatio(SentimentRatio sentimentRatio) {
        this.sentimentRatio = sentimentRatio;
    }

    public int getSocialMediaRatio() {
        return socialMediaRatio;
    }

    public void setSocialMediaRatio(int socialMediaRatio) {
        this.socialMediaRatio = socialMediaRatio;
    }

    public int getTraditionalMediaRatio() {
        return traditionalMediaRatio;
    }

    public void setTraditionalMediaRatio(int traditionalMediaRatio) {
        this.traditionalMediaRatio = traditionalMediaRatio;
    }

    public List<Integer> getTrendData() {
        return trendData;
    }

    public void setTrendData(List<Integer> trendData) {
        this.trendData = trendData;
    }

    public static class SentimentRatio {
        private int positive;
        private int neutral;
        private int negative;

        public int getPositive() {
            return positive;
        }

        public void setPositive(int positive) {
            this.positive = positive;
        }

        public int getNeutral() {
            return neutral;
        }

        public void setNeutral(int neutral) {
            this.neutral = neutral;
        }

        public int getNegative() {
            return negative;
        }

        public void setNegative(int negative) {
            this.negative = negative;
        }
    }
}
