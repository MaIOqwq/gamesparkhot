package com.example.opinion_analysis.model;

public class SentimentWordItemDTO {
    private String word;
    private int weight;
    private int count;

    public SentimentWordItemDTO() {}

    public SentimentWordItemDTO(String word, int weight, int count) {
        this.word = word;
        this.weight = weight;
        this.count = count;
    }

    public String getWord() { return word; }
    public void setWord(String word) { this.word = word; }
    public int getWeight() { return weight; }
    public void setWeight(int weight) { this.weight = weight; }
    public int getCount() { return count; }
    public void setCount(int count) { this.count = count; }
}
