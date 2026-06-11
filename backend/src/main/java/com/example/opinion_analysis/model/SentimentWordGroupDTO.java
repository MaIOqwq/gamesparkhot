package com.example.opinion_analysis.model;

import java.util.List;

public class SentimentWordGroupDTO {
    private String sentiment;
    private String label;
    private List<SentimentWordItemDTO> words;

    public SentimentWordGroupDTO() {}

    public SentimentWordGroupDTO(String sentiment, String label, List<SentimentWordItemDTO> words) {
        this.sentiment = sentiment;
        this.label = label;
        this.words = words;
    }

    public String getSentiment() { return sentiment; }
    public void setSentiment(String sentiment) { this.sentiment = sentiment; }
    public String getLabel() { return label; }
    public void setLabel(String label) { this.label = label; }
    public List<SentimentWordItemDTO> getWords() { return words; }
    public void setWords(List<SentimentWordItemDTO> words) { this.words = words; }
}
