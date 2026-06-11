package com.example.opinion_analysis.model;

import java.util.List;

public class TrendDTO {
    private String date;
    private int value;
    private List<TopContentDTO> topContents;

    public TrendDTO() {}

    public TrendDTO(String date, int value) {
        this.date = date;
        this.value = value;
    }

    public String getDate() {
        return date;
    }

    public void setDate(String date) {
        this.date = date;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }

    public List<TopContentDTO> getTopContents() {
        return topContents;
    }

    public void setTopContents(List<TopContentDTO> topContents) {
        this.topContents = topContents;
    }
}
