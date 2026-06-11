package com.example.opinion_analysis.model;

public class RegionDTO {
    private String name;
    private int value;

    public RegionDTO() {}

    public RegionDTO(String name, int value) {
        this.name = name;
        this.value = value;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}
