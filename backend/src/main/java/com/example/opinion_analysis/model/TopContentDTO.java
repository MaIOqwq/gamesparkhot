package com.example.opinion_analysis.model;

public class TopContentDTO {
    private String title;
    private String platform;
    private double hotValue;
    private double contributionRatio;

    public TopContentDTO() {}

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getPlatform() { return platform; }
    public void setPlatform(String platform) { this.platform = platform; }
    public double getHotValue() { return hotValue; }
    public void setHotValue(double hotValue) { this.hotValue = hotValue; }
    public double getContributionRatio() { return contributionRatio; }
    public void setContributionRatio(double contributionRatio) { this.contributionRatio = contributionRatio; }
}
