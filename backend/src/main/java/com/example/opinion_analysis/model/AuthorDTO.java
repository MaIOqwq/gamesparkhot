package com.example.opinion_analysis.model;

public class AuthorDTO {
    private String author;
    private int contentCount;
    private double totalHot;
    private double avgHot;

    public AuthorDTO() {}

    public AuthorDTO(String author, int contentCount, double totalHot, double avgHot) {
        this.author = author;
        this.contentCount = contentCount;
        this.totalHot = totalHot;
        this.avgHot = avgHot;
    }

    public String getAuthor() { return author; }
    public void setAuthor(String author) { this.author = author; }
    public int getContentCount() { return contentCount; }
    public void setContentCount(int contentCount) { this.contentCount = contentCount; }
    public double getTotalHot() { return totalHot; }
    public void setTotalHot(double totalHot) { this.totalHot = totalHot; }
    public double getAvgHot() { return avgHot; }
    public void setAvgHot(double avgHot) { this.avgHot = avgHot; }
}
