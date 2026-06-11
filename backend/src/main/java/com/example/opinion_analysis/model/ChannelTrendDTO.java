package com.example.opinion_analysis.model;

public class ChannelTrendDTO {
    private String date;
    private double bilibiliValue;
    private double ngaValue;
    private double ngaRatio;

    public ChannelTrendDTO() {}

    public String getDate() { return date; }
    public void setDate(String date) { this.date = date; }
    public double getBilibiliValue() { return bilibiliValue; }
    public void setBilibiliValue(double bilibiliValue) { this.bilibiliValue = bilibiliValue; }
    public double getNgaValue() { return ngaValue; }
    public void setNgaValue(double ngaValue) { this.ngaValue = ngaValue; }
    public double getNgaRatio() { return ngaRatio; }
    public void setNgaRatio(double ngaRatio) { this.ngaRatio = ngaRatio; }
}
