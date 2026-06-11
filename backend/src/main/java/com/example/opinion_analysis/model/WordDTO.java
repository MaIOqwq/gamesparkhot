package com.example.opinion_analysis.model;

public class WordDTO {
    private String word;
    private int weight;
    private Double sentimentScore;
    private String hotTitle;
    private String hotPlatform;
    private Double hotValue;

    public WordDTO() {}

    public WordDTO(String word, int weight) {
        this.word = word;
        this.weight = weight;
    }

    public WordDTO(String word, int weight, Double sentimentScore) {
        this.word = word;
        this.weight = weight;
        this.sentimentScore = sentimentScore;
    }

    public String getWord() { return word; }
    public void setWord(String word) { this.word = word; }
    public int getWeight() { return weight; }
    public void setWeight(int weight) { this.weight = weight; }
    public Double getSentimentScore() { return sentimentScore; }
    public void setSentimentScore(Double sentimentScore) { this.sentimentScore = sentimentScore; }
    public String getHotTitle() { return hotTitle; }
    public void setHotTitle(String hotTitle) { this.hotTitle = hotTitle; }
    public String getHotPlatform() { return hotPlatform; }
    public void setHotPlatform(String hotPlatform) { this.hotPlatform = hotPlatform; }
    public Double getHotValue() { return hotValue; }
    public void setHotValue(Double hotValue) { this.hotValue = hotValue; }
}
