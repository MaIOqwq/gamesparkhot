package com.example.opinion_analysis.model;

public class InfoItemDTO {
    private int id;
    private String title;
    private String source;
    private String time;
    private String sentiment;
    private int hotValue;
    private Integer hotChange;
    private Double hotChangePercent;
    private String trend;

    public InfoItemDTO() {}

    public InfoItemDTO(String source, String title, String time, String sentiment, int hotValue) {
        this.source = source;
        this.title = title;
        this.time = time;
        this.sentiment = sentiment;
        this.hotValue = hotValue;
    }

    public int getId() {
        return id;
    }

    public void setId(int id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getTime() {
        return time;
    }

    public void setTime(String time) {
        this.time = time;
    }

    public String getSentiment() {
        return sentiment;
    }

    public void setSentiment(String sentiment) {
        this.sentiment = sentiment;
    }

    public int getHotValue() {
        return hotValue;
    }

    public void setHotValue(int hotValue) {
        this.hotValue = hotValue;
    }

    public Integer getHotChange() {
        return hotChange;
    }

    public void setHotChange(Integer hotChange) {
        this.hotChange = hotChange;
    }

    public Double getHotChangePercent() {
        return hotChangePercent;
    }

    public void setHotChangePercent(Double hotChangePercent) {
        this.hotChangePercent = hotChangePercent;
    }

    public String getTrend() {
        return trend;
    }

    public void setTrend(String trend) {
        this.trend = trend;
    }
}
