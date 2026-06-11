package com.example.cleaner

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.logging.log4j.LogManager
import scala.collection.JavaConverters._

/**
 * 批处理数据清洗类
 * 用于处理历史数据，实现字段统一、文本标准化、热度计算等功能
 */
object BatchDataCleaner {
  private val logger = LogManager.getLogger(getClass)

  // 热度计算使用等权求和（经PCA验证各指标无显著差异）

  def main(args: Array[String]): Unit = {
    logger.info("Starting BatchDataCleaner...")

    // 创建SparkSession
    val spark = SparkSession.builder()
      .appName(ConfigManager.Spark.appName)
      .master(ConfigManager.Spark.master)
      .config("spark.executor.memory", ConfigManager.Spark.Executor.memory)
      .config("spark.executor.cores", ConfigManager.Spark.Executor.cores)
      .config("spark.driver.memory", ConfigManager.Spark.Driver.memory)
      .config("spark.sql.dialect", "mysql")
      .getOrCreate()

    try {
      // 处理B站数据
      processBiliData(spark)

      // 处理NGA数据
      processNgaData(spark)

      logger.info("BatchDataCleaner completed successfully")

    } catch {
      case e: Exception =>
        logger.error("Error in BatchDataCleaner", e)
        throw e
    } finally {
      spark.stop()
      logger.info("BatchDataCleaner stopped")
    }
  }

  /**
   * 处理B站数据
   */
  private def processBiliData(spark: SparkSession): Unit = {
    try {
      // 从Kafka读取数据
      val kafkaParams = Map[String, String](
        "kafka.bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
        "subscribe" -> ConfigManager.Kafka.Bili.topics.asScala.mkString(","),
        "startingOffsets" -> "earliest",
        "endingOffsets" -> "latest"
      )

      val df = spark.read
        .format("kafka")
        .options(kafkaParams)
        .load()
        .selectExpr("CAST(value AS STRING)")

      if (!df.isEmpty) {
        val jsonDF = spark.read.json(df.select("value").rdd.map(_.getString(0)))

        // 处理视频数据
        if (jsonDF.columns.contains("video_id")) {
          val videoDF = jsonDF.filter(col("video_id").isNotNull)
          if (!videoDF.isEmpty) {
            processBiliVideoData(videoDF, spark)
          }
        }

        // 处理评论数据
        if (jsonDF.columns.contains("comment_id")) {
          val commentDF = jsonDF.filter(col("comment_id").isNotNull)
          if (!commentDF.isEmpty) {
            processBiliCommentData(commentDF, spark)
          }
        }
      }
    } catch {
      case e: Exception =>
        logger.error("Error processing Bili data", e)
    }
  }

  /**
   * 处理NGA数据
   */
  private def processNgaData(spark: SparkSession): Unit = {
    try {
      // 从Kafka读取数据
      val kafkaParams = Map[String, String](
        "kafka.bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
        "subscribe" -> s"${ConfigManager.Kafka.Nga.Context.topics.asScala.mkString(",")},${ConfigManager.Kafka.Nga.Comment.topics.asScala.mkString(",")}",
        "startingOffsets" -> "earliest",
        "endingOffsets" -> "latest"
      )

      val df = spark.read
        .format("kafka")
        .options(kafkaParams)
        .load()
        .selectExpr("CAST(value AS STRING)")

      if (!df.isEmpty) {
        val jsonDF = spark.read.json(df.select("value").rdd.map(_.getString(0)))

        // 处理帖子基本信息（包含thread_id和title的帖子数据）
        if (jsonDF.columns.contains("thread_id") && jsonDF.columns.contains("title")) {
          val threadDF = jsonDF.filter(col("thread_id").isNotNull)
          if (!threadDF.isEmpty) {
            logger.info(s"Processing ${threadDF.count()} NGA thread records")
            processNgaThreadData(threadDF, spark)
          }
        }

        // 处理帖子内容（包含content和author的内容数据）
        if (jsonDF.columns.contains("content") && jsonDF.columns.contains("author")) {
          val contentDF = jsonDF.filter(col("content").isNotNull)
          if (!contentDF.isEmpty) {
            logger.info(s"Processing ${contentDF.count()} NGA content records")
            processNgaContentData(contentDF, spark)
          }
        }
      }
    } catch {
      case e: Exception =>
        logger.error("Error processing Nga data", e)
    }
  }

  /**
   * 处理B站视频数据
   */
  private def processBiliVideoData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      val cleanedVideoDF = df
        .filter(col("video_id").isNotNull)
        .dropDuplicates("video_id")
        .withColumn("create_time", from_unixtime(col("create_time").cast("long")))
        .withColumn("video_play_count", col("video_play_count").cast("int"))
        .withColumn("video_favorite_count", col("video_favorite_count").cast("int"))
        .withColumn("video_share_count", col("video_share_count").cast("int"))
        .withColumn("video_coin_count", col("video_coin_count").cast("int"))
        .withColumn("video_danmaku", col("video_danmaku").cast("int"))
        .withColumn("video_comment", col("video_comment").cast("int"))
        .withColumn("liked_count", col("liked_count").cast("int"))
        .withColumn("disliked_count", col("disliked_count").cast("int"))
        .withColumn("title", substring(col("title"), 1, 500))
        .withColumn("desc", substring(col("desc"), 1, 500))
        .filter(col("source_keyword").isNotNull)
        .withColumn("cleaned_at", current_timestamp())

      // 字段统一
      val standardizedDF = cleanedVideoDF
        .withColumn("raw_id", col("video_id").cast("long"))
        .withColumn("platform", lit("bilibili"))
        .withColumn("title_clean", DataCleanerUtils.cleanTitle(col("title")))
        .withColumn("content_clean", DataCleanerUtils.cleanContent(col("desc")))
        .withColumn("view_count", col("video_play_count"))
        .withColumn("like_count", col("liked_count"))
        .withColumn("coin_count", col("video_coin_count"))
        .withColumn("favorite_count", col("video_favorite_count"))
        .withColumn("share_count", col("video_share_count"))
        .withColumn("comment_count", col("video_comment"))
        .withColumn("publish_time", col("create_time"))
        .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)
        .withColumn("keyword", col("source_keyword"))

      // 过滤短文本
      val filteredDF = standardizedDF
        .filter(length(col("title_clean")) >= 5)
        .filter(length(col("content_clean")) >= 5)

      // 计算热度
      val withHotScore = calculateBiliHotScore(filteredDF)

      // 选择最终字段
      val finalDF = withHotScore.select(
        col("raw_id"),
        col("platform"),
        col("title_clean"),
        col("content_clean"),
        col("view_count"),
        col("like_count"),
        col("coin_count"),
        col("favorite_count"),
        col("share_count"),
        col("comment_count"),
        col("publish_time"),
        col("time_diff"),
        col("hot_raw"),
        col("hot_norm"),
        col("hot_score"),
        col("keyword")
      )

      // 存储到MariaDB
      saveToDatabase(finalDF)

      logger.info(s"Processed ${finalDF.count()} video records")
    } catch {
      case e: Exception =>
        logger.error("Error processing video data", e)
    }
  }

  /**
   * 处理B站评论数据
   */
  private def processBiliCommentData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      val cleanedCommentDF = df
        .filter(col("comment_id").isNotNull)
        .dropDuplicates("comment_id")
        .withColumn("create_time", from_unixtime(col("create_time").cast("long")))
        .withColumn("like_count", col("like_count").cast("int"))
        .withColumn("content", substring(col("content"), 1, 1000))
        .filter(col("video_id").isNotNull)
        .filter(col("user_id").isNotNull)
        .withColumn("cleaned_at", current_timestamp())

      // 字段统一
      val standardizedDF = cleanedCommentDF
        .withColumn("raw_id", col("comment_id").cast("long"))
        .withColumn("platform", lit("bilibili"))
        .withColumn("title_clean", lit(""))
        .withColumn("content_clean", DataCleanerUtils.cleanContent(col("content")))
        .withColumn("view_count", lit(0))
        .withColumn("like_count", col("like_count"))
        .withColumn("coin_count", lit(0))
        .withColumn("favorite_count", lit(0))
        .withColumn("share_count", lit(0))
        .withColumn("comment_count", lit(1))
        .withColumn("publish_time", col("create_time"))
        .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)

      // 过滤短文本
      val filteredDF = standardizedDF
        .filter(length(col("content_clean")) >= 5)

      // 计算热度
      val withHotScore = calculateBiliHotScore(filteredDF)

      // 选择最终字段
      val finalDF = withHotScore.select(
        col("raw_id"),
        col("platform"),
        col("title_clean"),
        col("content_clean"),
        col("view_count"),
        col("like_count"),
        col("coin_count"),
        col("favorite_count"),
        col("share_count"),
        col("comment_count"),
        col("publish_time"),
        col("time_diff"),
        col("hot_raw"),
        col("hot_norm"),
        col("hot_score"),
        col("keyword")
      )

      // 存储到MariaDB
      saveToDatabase(finalDF)

      logger.info(s"Processed ${finalDF.count()} comment records")
    } catch {
      case e: Exception =>
        logger.error("Error processing comment data", e)
    }
  }

  /**
   * 处理NGA帖子基本信息
   */
  private def processNgaThreadData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      val cleanedThreadDF = df
        .select("data.*", "keyword")
        .filter(col("thread_id").isNotNull)
        .dropDuplicates("thread_id")
        .withColumn("replies", col("replies").cast("int"))
        .withColumn("post_date", to_date(col("post_date"), "yyyy-MM-dd"))
        .withColumn("title", substring(col("title"), 1, 255))
        .filter(col("author").isNotNull)
        .filter(col("url").isNotNull)
        .filter(col("keyword").isNotNull)
        .withColumn("cleaned_at", current_timestamp())

      // 字段统一
      val standardizedDF = cleanedThreadDF
        .withColumn("raw_id", col("thread_id").cast("long"))
        .withColumn("platform", lit("nga"))
        .withColumn("title_clean", DataCleanerUtils.cleanTitle(col("title")))
        .withColumn("content_clean", lit(""))
        .withColumn("view_count", lit(0))
        .withColumn("like_count", lit(0))
        .withColumn("coin_count", lit(0))
        .withColumn("favorite_count", lit(0))
        .withColumn("share_count", lit(0))
        .withColumn("comment_count", col("replies"))
        .withColumn("publish_time", col("post_date"))
        .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)

      // 过滤短文本
      val filteredDF = standardizedDF
        .filter(length(col("title_clean")) >= 5)

      // 计算热度
      val withHotScore = calculateNgaHotScore(filteredDF)

      // 选择最终字段
      val finalDF = withHotScore.select(
        col("raw_id"),
        col("platform"),
        col("title_clean"),
        col("content_clean"),
        col("view_count"),
        col("like_count"),
        col("coin_count"),
        col("favorite_count"),
        col("share_count"),
        col("comment_count"),
        col("publish_time"),
        col("time_diff"),
        col("hot_raw"),
        col("hot_norm"),
        col("hot_score"),
        col("keyword")
      )

      // 存储到MariaDB
      saveToDatabase(finalDF)

      logger.info(s"Processed ${finalDF.count()} thread records")
    } catch {
      case e: Exception =>
        logger.error("Error processing thread data", e)
    }
  }

  /**
   * 处理NGA帖子内容
   */
  private def processNgaContentData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      val cleanedContentDF = df
        .select("data.*", "keyword")
        .filter(col("thread_id").isNotNull)
        .withColumn("content", substring(col("content"), 1, 5000))
        .filter(col("author").isNotNull)
        .filter(col("type").isin("main", "reply"))
        .filter(col("keyword").isNotNull)
        .withColumn("cleaned_at", current_timestamp())

      // 字段统一
      val standardizedDF = cleanedContentDF
        .withColumn("raw_id", col("thread_id").cast("long"))
        .withColumn("platform", lit("nga"))
        .withColumn("title_clean", lit(""))
        .withColumn("content_clean", DataCleanerUtils.cleanContent(col("content")))
        .withColumn("view_count", lit(0))
        .withColumn("like_count", lit(0))
        .withColumn("coin_count", lit(0))
        .withColumn("favorite_count", lit(0))
        .withColumn("share_count", lit(0))
        .withColumn("comment_count", when(col("type") === "main", lit(1)).otherwise(lit(0)))
        .withColumn("publish_time", current_timestamp())
        .withColumn("time_diff", lit(0.0))

      // 过滤短文本
      val filteredDF = standardizedDF
        .filter(length(col("content_clean")) >= 5)

      // 计算热度
      val withHotScore = calculateNgaHotScore(filteredDF)

      // 选择最终字段
      val finalDF = withHotScore.select(
        col("raw_id"),
        col("platform"),
        col("title_clean"),
        col("content_clean"),
        col("view_count"),
        col("like_count"),
        col("coin_count"),
        col("favorite_count"),
        col("share_count"),
        col("comment_count"),
        col("publish_time"),
        col("time_diff"),
        col("hot_raw"),
        col("hot_norm"),
        col("hot_score"),
        col("keyword")
      )

      // 存储到MariaDB
      saveToDatabase(finalDF)

      logger.info(s"Processed ${finalDF.count()} content records")
    } catch {
      case e: Exception =>
        logger.error("Error processing content data", e)
    }
  }

  /**
   * 计算B站热度值
   */
  private def calculateBiliHotScore(df: org.apache.spark.sql.DataFrame): org.apache.spark.sql.DataFrame = {
    DataCleanerUtils.calculateHotScore(df)
  }

  /**
   * 计算NGA热度值
   */
  private def calculateNgaHotScore(df: org.apache.spark.sql.DataFrame): org.apache.spark.sql.DataFrame = {
    DataCleanerUtils.calculateHotScore(df)
  }

  /**
   * 保存数据到数据库
   */
  private def saveToDatabase(df: org.apache.spark.sql.DataFrame): Unit = {
    df.foreachPartition { iterator: Iterator[org.apache.spark.sql.Row] =>
      import java.sql._
      var conn: Connection = null
      var stmt: PreparedStatement = null
      try {
        Class.forName("org.mariadb.jdbc.Driver")
        conn = DriverManager.getConnection(
          s"${ConfigManager.MySQL.Standardized.fullUrl}?useSSL=false&useUnicode=true&characterEncoding=utf8mb4",
          ConfigManager.MySQL.user,
          ConfigManager.MySQL.password
        )
        val sql = "INSERT INTO standardized_data (raw_id, platform, title_clean, content_clean, view_count, like_count, coin_count, favorite_count, share_count, comment_count, publish_time, time_diff, hot_raw, hot_norm, hot_score, keyword) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        stmt = conn.prepareStatement(sql)
        iterator.foreach { row =>
            stmt.setLong(1, row.getAs[Long]("raw_id"))
            stmt.setString(2, row.getAs[String]("platform"))
            stmt.setString(3, row.getAs[String]("title_clean"))
            stmt.setString(4, row.getAs[String]("content_clean"))
            stmt.setInt(5, row.getAs[Int]("view_count"))
            stmt.setInt(6, row.getAs[Int]("like_count"))
            stmt.setInt(7, row.getAs[Int]("coin_count"))
            stmt.setInt(8, row.getAs[Int]("favorite_count"))
            stmt.setInt(9, row.getAs[Int]("share_count"))
            stmt.setInt(10, row.getAs[Int]("comment_count"))
            val publishTimeStr = row.getAs[String]("publish_time")
            val publishTime = java.sql.Timestamp.valueOf(publishTimeStr)
            stmt.setTimestamp(11, publishTime)
            stmt.setDouble(12, row.getAs[Double]("time_diff"))
            stmt.setDouble(13, row.getAs[Double]("hot_raw"))
            stmt.setDouble(14, row.getAs[Double]("hot_norm"))
            stmt.setDouble(15, row.getAs[Double]("hot_score"))
            stmt.setString(16, row.getAs[String]("keyword"))
            stmt.addBatch()
          }
        stmt.executeBatch()
        ()
      } catch {
        case e: Exception =>
          logger.error("Error writing to database", e)
          throw e
      } finally {
        if (stmt != null) stmt.close()
        if (conn != null) conn.close()
      }
    }
  }
}
