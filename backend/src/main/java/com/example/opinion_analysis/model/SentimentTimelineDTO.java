package com.example.opinion_analysis.model;

public class SentimentTimelineDTO {
    private String date;
    private int positive;
    private int neutral;
    private int negative;

    public SentimentTimelineDTO() {}

    public SentimentTimelineDTO(String date, int positive, int neutral, int negative) {
        this.date = date;
        this.positive = positive;
        this.neutral = neutral;
        this.negative = negative;
    }

    public String getDate() { return date; }
    public void setDate(String date) { this.date = date; }
    public int getPositive() { return positive; }
    public void setPositive(int positive) { this.positive = positive; }
    public int getNeutral() { return neutral; }
    public void setNeutral(int neutral) { this.neutral = neutral; }
    public int getNegative() { return negative; }
    public void setNegative(int negative) { this.negative = negative; }
}
