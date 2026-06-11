package com.example.opinion_analysis.model;

import javax.persistence.*;
import java.util.Date;

@Entity
@Table(name = "standardized_data")
public class StandardizedData {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "raw_id", nullable = false, length = 64)
    private String rawId;

    @Column(name = "platform", nullable = false)
    private int platform;

    @Column(name = "type", length = 16)
    private String type;

    @Column(name = "author", nullable = false, length = 128)
    private String author;

    @Column(name = "title_clean", length = 500)
    private String titleClean;

    @Column(name = "content_clean", columnDefinition = "TEXT")
    private String contentClean;

    @Column(name = "publish_time", nullable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date publishTime;

    @Column(name = "keyword", nullable = false, length = 100)
    private String keyword;

    @Column(name = "view_count", nullable = false)
    private int viewCount = 0;

    @Column(name = "like_count", nullable = false)
    private int likeCount = 0;

    @Column(name = "comment_count", nullable = false)
    private int commentCount = 0;

    @Column(name = "coin_count", nullable = false)
    private int coinCount = 0;

    @Column(name = "favorite_count", nullable = false)
    private int favoriteCount = 0;

    @Column(name = "share_count", nullable = false)
    private int shareCount = 0;

    @Column(name = "danmaku_count", nullable = false)
    private int danmakuCount = 0;

    @Column(name = "is_hot_reply", nullable = false)
    private int isHotReply = 0;

    @Column(name = "author_fans", nullable = false)
    private int authorFans = 0;

    @Column(name = "author_level", nullable = false)
    private int authorLevel = 0;

    @Column(name = "author_post_count", nullable = false)
    private int authorPostCount = 0;

    @Column(name = "has_image", nullable = false)
    private int hasImage = 0;

    @Column(name = "has_video", nullable = false)
    private int hasVideo = 0;

    @Column(name = "board_name", length = 50)
    private String boardName;

    @Column(name = "hot_raw", nullable = false)
    private double hotRaw;

    @Column(name = "hot_norm", nullable = false)
    private double hotNorm;

    @Column(name = "hot_score", nullable = false)
    private double hotScore;

    @Column(name = "text_length", nullable = false)
    private int textLength = 0;

    @Column(name = "sentiment_score", nullable = false)
    private float sentimentScore = 0;

    @Column(name = "created_at", nullable = false, updatable = false)
    @Temporal(TemporalType.TIMESTAMP)
    private Date createdAt;

    // Getters and setters
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getRawId() {
        return rawId;
    }

    public void setRawId(String rawId) {
        this.rawId = rawId;
    }

    public int getPlatform() {
        return platform;
    }

    public void setPlatform(int platform) {
        this.platform = platform;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public String getAuthor() {
        return author;
    }

    public void setAuthor(String author) {
        this.author = author;
    }

    public String getTitleClean() {
        return titleClean;
    }

    public void setTitleClean(String titleClean) {
        this.titleClean = titleClean;
    }

    public String getContentClean() {
        return contentClean;
    }

    public void setContentClean(String contentClean) {
        this.contentClean = contentClean;
    }

    public Date getPublishTime() {
        return publishTime;
    }

    public void setPublishTime(Date publishTime) {
        this.publishTime = publishTime;
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public int getViewCount() {
        return viewCount;
    }

    public void setViewCount(int viewCount) {
        this.viewCount = viewCount;
    }

    public int getLikeCount() {
        return likeCount;
    }

    public void setLikeCount(int likeCount) {
        this.likeCount = likeCount;
    }

    public int getCommentCount() {
        return commentCount;
    }

    public void setCommentCount(int commentCount) {
        this.commentCount = commentCount;
    }

    public int getCoinCount() {
        return coinCount;
    }

    public void setCoinCount(int coinCount) {
        this.coinCount = coinCount;
    }

    public int getFavoriteCount() {
        return favoriteCount;
    }

    public void setFavoriteCount(int favoriteCount) {
        this.favoriteCount = favoriteCount;
    }

    public int getShareCount() {
        return shareCount;
    }

    public void setShareCount(int shareCount) {
        this.shareCount = shareCount;
    }

    public int getDanmakuCount() {
        return danmakuCount;
    }

    public void setDanmakuCount(int danmakuCount) {
        this.danmakuCount = danmakuCount;
    }

    public int getIsHotReply() {
        return isHotReply;
    }

    public void setIsHotReply(int isHotReply) {
        this.isHotReply = isHotReply;
    }

    public int getAuthorFans() {
        return authorFans;
    }

    public void setAuthorFans(int authorFans) {
        this.authorFans = authorFans;
    }

    public int getAuthorLevel() {
        return authorLevel;
    }

    public void setAuthorLevel(int authorLevel) {
        this.authorLevel = authorLevel;
    }

    public int getAuthorPostCount() {
        return authorPostCount;
    }

    public void setAuthorPostCount(int authorPostCount) {
        this.authorPostCount = authorPostCount;
    }

    public int getHasImage() {
        return hasImage;
    }

    public void setHasImage(int hasImage) {
        this.hasImage = hasImage;
    }

    public int getHasVideo() {
        return hasVideo;
    }

    public void setHasVideo(int hasVideo) {
        this.hasVideo = hasVideo;
    }

    public String getBoardName() {
        return boardName;
    }

    public void setBoardName(String boardName) {
        this.boardName = boardName;
    }

    public double getHotRaw() {
        return hotRaw;
    }

    public void setHotRaw(double hotRaw) {
        this.hotRaw = hotRaw;
    }

    public double getHotNorm() {
        return hotNorm;
    }

    public void setHotNorm(double hotNorm) {
        this.hotNorm = hotNorm;
    }

    public double getHotScore() {
        return hotScore;
    }

    public void setHotScore(double hotScore) {
        this.hotScore = hotScore;
    }

    public int getTextLength() {
        return textLength;
    }

    public void setTextLength(int textLength) {
        this.textLength = textLength;
    }

    public float getSentimentScore() {
        return sentimentScore;
    }

    public void setSentimentScore(float sentimentScore) {
        this.sentimentScore = sentimentScore;
    }

    public Date getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Date createdAt) {
        this.createdAt = createdAt;
    }

    @PrePersist
    protected void onCreate() {
        createdAt = new Date();
    }
}
