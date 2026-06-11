package com.example.opinion_analysis.repository;

import com.example.opinion_analysis.model.StandardizedData;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Date;
import java.util.List;

public interface StandardizedDataRepository extends JpaRepository<StandardizedData, Long> {

    // 根据关键词查询数据
    List<StandardizedData> findByKeyword(String keyword);
    
    // 查询所有数据（不筛选关键词）
    @Query("SELECT s FROM StandardizedData s")
    List<StandardizedData> findAllData();

    // 根据关键词和时间范围查询数据
    List<StandardizedData> findByKeywordAndPublishTimeBetween(String keyword, Date startDate, Date endDate);

    // 根据时间范围查询所有数据
    List<StandardizedData> findByPublishTimeBetween(Date startDate, Date endDate);

    // 查询所有关键词
    @Query("SELECT DISTINCT s.keyword FROM StandardizedData s")
    List<String> findDistinctKeywords();

    // 计算平均热度
    @Query("SELECT AVG(s.hotScore) FROM StandardizedData s WHERE s.keyword = :keyword")
    Double calculateAverageHotScore(@Param("keyword") String keyword);

    // 计算情感占比
    @Query("SELECT COUNT(s) FROM StandardizedData s WHERE s.keyword = :keyword AND s.sentimentScore > 0.2")
    Long countPositiveSentiment(@Param("keyword") String keyword);

    @Query("SELECT COUNT(s) FROM StandardizedData s WHERE s.keyword = :keyword AND s.sentimentScore BETWEEN -0.2 AND 0.2")
    Long countNeutralSentiment(@Param("keyword") String keyword);

    @Query("SELECT COUNT(s) FROM StandardizedData s WHERE s.keyword = :keyword AND s.sentimentScore < -0.2")
    Long countNegativeSentiment(@Param("keyword") String keyword);

    // 计算平台分布
    @Query("SELECT s.platform, COUNT(s) FROM StandardizedData s WHERE s.keyword = :keyword GROUP BY s.platform")
    List<Object[]> countByPlatform(@Param("keyword") String keyword);

    // 获取热点词（这里简化处理，实际应该从内容中提取）
    @Query("SELECT s.titleClean, MAX(s.hotScore) FROM StandardizedData s WHERE s.keyword = :keyword GROUP BY s.titleClean ORDER BY MAX(s.hotScore) DESC")
    List<Object[]> findHotWords(@Param("keyword") String keyword);

    // 获取热度排行榜（按关键词）
    @Query("SELECT s FROM StandardizedData s WHERE s.keyword = :keyword ORDER BY s.hotScore DESC")
    List<StandardizedData> findHotRanking(@Param("keyword") String keyword);

    // 根据关键词和时间范围获取热度排行榜
    @Query("SELECT s FROM StandardizedData s WHERE s.keyword = :keyword AND s.publishTime BETWEEN :startDate AND :endDate ORDER BY s.hotScore DESC, s.hotRaw DESC")
    List<StandardizedData> findHotRankingByKeywordAndTimeRange(@Param("keyword") String keyword, @Param("startDate") Date startDate, @Param("endDate") Date endDate);

    // 按关键词+时间范围查询，按 hot_raw 取 top 100（用于后续按 hot_score 精排）
    @Query(value = "SELECT * FROM standardized_data WHERE keyword = ?1 AND publish_time BETWEEN ?2 AND ?3 ORDER BY hot_raw DESC LIMIT 100", nativeQuery = true)
    List<StandardizedData> findTop100ByKeywordAndTimeRangeOrderByHotRaw(String keyword, Date startDate, Date endDate);

    // 按时间范围查询（全部数据），按 hot_raw 取 top 100
    @Query(value = "SELECT * FROM standardized_data WHERE publish_time BETWEEN ?1 AND ?2 ORDER BY hot_raw DESC LIMIT 100", nativeQuery = true)
    List<StandardizedData> findTop100ByTimeRangeOrderByHotRaw(Date startDate, Date endDate);

    // 计算近7天热度趋势
    @Query("SELECT s.publishTime, AVG(s.hotScore) FROM StandardizedData s WHERE s.keyword = :keyword AND s.publishTime BETWEEN :startDate AND :endDate GROUP BY s.publishTime ORDER BY s.publishTime")
    List<Object[]> calculateHotTrend(@Param("keyword") String keyword, @Param("startDate") Date startDate, @Param("endDate") Date endDate);

    // 查询标题和内容用于词云生成
    @Query("SELECT s.titleClean, s.contentClean FROM StandardizedData s WHERE s.keyword = :keyword")
    List<Object[]> findTitlesAndContentByKeyword(@Param("keyword") String keyword);

    // 统计指定时间之后的数据量
    long countByPublishTimeAfter(Date date);

    // 查询最新一条数据的发布时间
    @Query("SELECT MAX(s.publishTime) FROM StandardizedData s")
    Date findLastPublishTime();

    // 按2小时窗口统计今日数据量
    @Query(value = "SELECT FLOOR(HOUR(publish_time)/2)*2 as h, COUNT(*) as c FROM standardized_data WHERE publish_time >= ?1 GROUP BY FLOOR(HOUR(publish_time)/2)*2 ORDER BY h", nativeQuery = true)
    List<Object[]> countByHourSince(Date startTime);

    // 查询最新5条数据
    @Query(value = "SELECT title_clean, content_clean, platform, hot_raw, publish_time FROM standardized_data ORDER BY publish_time DESC LIMIT 5", nativeQuery = true)
    List<Object[]> findLatestTop5();

    // 作者排行：按总热度排序
    @Query(value = "SELECT author, COUNT(*) as content_count, SUM(hot_raw) as total_hot, ROUND(AVG(hot_raw), 2) as avg_hot FROM standardized_data WHERE keyword = ?1 AND author IS NOT NULL AND author != '' GROUP BY author ORDER BY total_hot DESC LIMIT 20", nativeQuery = true)
    List<Object[]> findAuthorRankingByKeyword(String keyword);

    // 作者排行：按关键词+时间范围
    @Query(value = "SELECT author, COUNT(*) as content_count, SUM(hot_raw) as total_hot, ROUND(AVG(hot_raw), 2) as avg_hot FROM standardized_data WHERE keyword = ?1 AND publish_time BETWEEN ?2 AND ?3 AND author IS NOT NULL AND author != '' GROUP BY author ORDER BY total_hot DESC LIMIT 20", nativeQuery = true)
    List<Object[]> findAuthorRankingByKeywordAndTimeRange(String keyword, Date startDate, Date endDate);
}
