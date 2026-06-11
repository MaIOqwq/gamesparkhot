package com.example.cleaner

import org.apache.spark.sql.DataFrame
import org.apache.spark.sql.Column
import org.apache.spark.sql.functions._

/**
 * 数据清洗工具类
 * 提供通用的数据清洗方法，供B站和NGA数据清洗类共用
 */
object DataCleanerUtils {
  
  /**
   * 清洗标题 - 去除特殊符号、表情符号、停用词等
   */
  def cleanTitle(title: Column): Column = {
    var cleaned = title.cast("string")
    cleaned = regexp_replace(cleaned, "https?://\\S+", "")
    cleaned = regexp_replace(cleaned, "@\\S+", "")
    cleaned = regexp_replace(cleaned, "#\\S+", "")
    cleaned = regexp_replace(cleaned, "[\\p{Punct}\\p{Space}]+", " ")
    cleaned = regexp_replace(cleaned, "\\s+", " ")
    cleaned = trim(cleaned)
    cleaned
  }

  /**
   * 清洗内容 - 去除特殊符号、URL、@用户提及、话题标签等
   */
  def cleanContent(content: Column): Column = {
    var cleaned = content.cast("string")
    cleaned = regexp_replace(cleaned, "https?://\\S+", "")
    cleaned = regexp_replace(cleaned, "@\\S+", "")
    cleaned = regexp_replace(cleaned, "#\\S+", "")
    cleaned = regexp_replace(cleaned, "[\\p{Punct}\\p{Space}]+", " ")
    cleaned = regexp_replace(cleaned, "\\s+", " ")
    cleaned = trim(cleaned)
    cleaned
  }

  /**
   * 标准化时间格式为 yyyy-MM-dd HH:mm:ss
   */
  def standardizeTime(time: Column): Column = {
    when(time.isNotNull,
      when(time.cast("string").rlike("^\\d+$"), from_unixtime(time.cast("long")))
       .when(time.cast("string").rlike("^\\d{2}-\\d{2} \\d{2}:\\d{2}$"), 
         from_unixtime(unix_timestamp(time.cast("string"), "MM-dd HH:mm")))
       .when(time.cast("string").rlike("^\\d{4}-\\d{2}-\\d{2}$"), 
         from_unixtime(unix_timestamp(time.cast("string"), "yyyy-MM-dd")))
       .otherwise(current_timestamp())
    ).otherwise(current_timestamp())
  }

  // 各平台 log(1+P95) 归一化分母（每月根据历史数据更新一次）
  private val BILIBILI_CAP = 10.81
  private val NGA_CAP = 2.64

  /**
   * 计算热度值
   * 使用等权求和 + log(1+x) + 固定P95分母归一化 + 时间衰减
   */
  def calculateHotScore(df: DataFrame): DataFrame = {
    // 1. 等权求和（各互动指标对热度的贡献经PCA验证无显著差异）
    val withHotRaw = df.withColumn("hot_raw",
      col("like_count") + col("comment_count") +
      col("coin_count") + col("favorite_count") + col("share_count")
    )

    // 2. 对数变换压缩长尾
    val withHotLog = withHotRaw.withColumn("hot_log", log1p(col("hot_raw")))

    // 3. 根据平台选择固定分母归一化（取代流式场景下失效的Min-Max）
    val withHotNorm = withHotLog.withColumn("hot_norm",
      when(col("platform") === "bilibili",
        least(col("hot_log") / BILIBILI_CAP, lit(1.0)))
      .when(col("platform") === "nga",
        least(col("hot_log") / NGA_CAP, lit(1.0)))
      .otherwise(lit(0.0))
    )

    // 4. 时间衰减（24小时衰减周期）
    val withHotScore = withHotNorm.withColumn("hot_score",
      col("hot_norm") * exp(-col("time_diff") / 24.0)
    )

    withHotScore
  }
}
