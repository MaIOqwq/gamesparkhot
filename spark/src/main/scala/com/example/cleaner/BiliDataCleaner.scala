package com.example.cleaner

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.streaming._
import org.apache.spark.streaming.kafka010._
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.logging.log4j.LogManager
import scala.collection.Iterator

/**
 * B站数据清洗类
 * 实现完整的数据清洗流程：去重、空值过滤、异常值清洗、字段统一、文本标准化、热度计算
 */
object BiliDataCleaner {
  private val logger = LogManager.getLogger(getClass)

  // 热度计算权重
  private val W1 = 1.0  // 点赞权重
  private val W2 = 1.5  // 评论权重
  private val W3 = 1.2  // 投币、收藏、分享权重

  def main(args: Array[String]): Unit = {
    logger.info("Starting BiliDataCleaner...")

    // 启动Kafka到Spark的传输
    KafkaToSparkTransmitter.startTransmission(
      appName = ConfigManager.Spark.appName,
      master = ConfigManager.Spark.master,
      batchDuration = ConfigManager.Spark.Streaming.batchDuration,
      kafkaDStreamCreator = KafkaToSparkTransmitter.createBiliKafkaDStream,
      messageProcessor = processBiliData
    )
  }

  /**
   * 处理B站数据的消息处理器
   */
  private def processBiliData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    logger.info(s"Received Bili data batch with ${df.count()} records")
    logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")
    
    // 检查是否有数据
    if (df.isEmpty) {
      logger.info("No Bili data to process")
      return
    }
    
    // 检查数据结构
    if (df.columns.contains("data")) {
      logger.info("Data contains nested 'data' field, extracting data...")
      
      // 先检查数据类型：视频数据（context）或评论数据（comment）
      val sampleData = df.select("data").limit(1)
      if (!sampleData.isEmpty) {
        // 检查data字段的结构
        val dataRow = sampleData.first().getAs[org.apache.spark.sql.Row]("data")
        val dataSchema = dataRow.schema
        
        // 判断是视频数据还是评论数据
        if (dataSchema.fieldNames.contains("video_id") && dataSchema.fieldNames.contains("title")) {
          logger.info("Detected video data (contains video_id and title)")
          // 提取视频数据
          val videoDF = df.select(
            "data.video_id",
            "data.user_id",
            "data.liked_count",
            "data.title",
            "data.desc",
            "data.create_time",
            "data.disliked_count",
            "data.video_play_count",
            "data.video_favorite_count",
            "data.video_share_count",
            "data.video_coin_count",
            "data.video_danmaku",
            "data.video_comment",
            "source_keyword",
            "timestamp"
          )
          logger.info(s"Extracted ${videoDF.count()} video records")
          logger.info(s"Video columns: ${videoDF.columns.mkString(", ")}")
          
          val validVideoDF = videoDF.filter(col("video_id").isNotNull)
          if (!validVideoDF.isEmpty) {
            logger.info(s"Processing ${validVideoDF.count()} valid video records")
            processVideoData(validVideoDF, spark)
          }
          
        } else if (dataSchema.fieldNames.contains("comment_id") && dataSchema.fieldNames.contains("content")) {
          logger.info("Detected comment data (contains comment_id and content)")
          // 提取评论数据
          val commentDF = df.select(
            "data.user_id",
            "data.comment_id",
            "data.video_id",
            "data.content",
            "data.create_time",
            "data.like_count",
            "source_keyword",
            "timestamp"
          )
          logger.info(s"Extracted ${commentDF.count()} comment records")
          logger.info(s"Comment columns: ${commentDF.columns.mkString(", ")}")
          
          val validCommentDF = commentDF.filter(col("comment_id").isNotNull)
          if (!validCommentDF.isEmpty) {
            logger.info(s"Processing ${validCommentDF.count()} valid comment records")
            processCommentData(validCommentDF, spark)
          }
          
        } else {
          logger.warn("Unknown data type, trying to extract all fields")
          val extractedDF = df.select("data.*", "source_keyword", "timestamp")
          logger.info(s"Extracted ${extractedDF.count()} records")
          logger.info(s"Columns: ${extractedDF.columns.mkString(", ")}")
          
          // 尝试处理视频数据
          if (extractedDF.columns.contains("video_id") && extractedDF.columns.contains("title")) {
            val videoDF = extractedDF.filter(col("video_id").isNotNull)
            if (!videoDF.isEmpty) {
              logger.info(s"Processing ${videoDF.count()} video records")
              processVideoData(videoDF, spark)
            }
          }
          
          // 尝试处理评论数据
          if (extractedDF.columns.contains("comment_id") && extractedDF.columns.contains("content")) {
            val commentDF = extractedDF.filter(col("comment_id").isNotNull)
            if (!commentDF.isEmpty) {
              logger.info(s"Processing ${commentDF.count()} comment records")
              processCommentData(commentDF, spark)
            }
          }
        }
      }
      
    } else {
      logger.info("Data does not contain 'data' field, processing directly...")
      
      // 处理视频数据
      if (df.columns.contains("video_id")) {
        val videoDF = df.filter(col("video_id").isNotNull)
        if (!videoDF.isEmpty) {
          logger.info(s"Processing ${videoDF.count()} video records")
          processVideoData(videoDF, spark)
        } else {
          logger.info("No video data found (video_id is null)")
        }
      } else {
        logger.info("No video data found (missing video_id column)")
      }
      
      // 处理评论数据
      if (df.columns.contains("comment_id")) {
        val commentDF = df.filter(col("comment_id").isNotNull)
        if (!commentDF.isEmpty) {
          logger.info(s"Processing ${commentDF.count()} comment records")
          processCommentData(commentDF, spark)
        } else {
          logger.info("No comment data found (comment_id is null)")
        }
      } else {
        logger.info("No comment data found (missing comment_id column)")
      }
    }
  }

  /**
   * 处理视频数据 - 完整的数据清洗流程
   */
  def processVideoData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      logger.info("Starting video data cleaning process...")
      logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")
      
      // 导入隐式编码器
      import spark.implicits._

      // 检查数据格式
      if (!df.columns.contains("video_id")) {
        logger.error("DataFrame does not contain video_id column, skipping processing")
        return
      }

      // 检查是否有数据
      if (df.isEmpty) {
        logger.info("No video data to process")
        return
      }

      // 1. 数据读取与预处理
      var cleanedDF = df.filter(col("video_id").isNotNull)

      // 2. 去重处理
      cleanedDF = cleanedDF.dropDuplicates("video_id")

      // 3. 空值过滤
      cleanedDF = cleanedDF
        .filter(col("title").isNotNull && col("title") =!= "")
        .filter(col("source_keyword").isNotNull && col("source_keyword") =!= "")

      // 4. 异常值清洗
      cleanedDF = cleanedDF
        .withColumn("video_play_count", when(col("video_play_count").isNotNull && col("video_play_count") >= 0, col("video_play_count")).otherwise(0))
        .withColumn("video_favorite_count", when(col("video_favorite_count").isNotNull && col("video_favorite_count") >= 0, col("video_favorite_count")).otherwise(0))
        .withColumn("video_share_count", when(col("video_share_count").isNotNull && col("video_share_count") >= 0, col("video_share_count")).otherwise(0))
        .withColumn("video_coin_count", when(col("video_coin_count").isNotNull && col("video_coin_count") >= 0, col("video_coin_count")).otherwise(0))
        .withColumn("video_danmaku", when(col("video_danmaku").isNotNull && col("video_danmaku") >= 0, col("video_danmaku")).otherwise(0))
        .withColumn("video_comment", when(col("video_comment").isNotNull && col("video_comment") >= 0, col("video_comment")).otherwise(0))
        .withColumn("liked_count", when(col("liked_count").isNotNull && col("liked_count") >= 0, col("liked_count")).otherwise(0))
        .withColumn("disliked_count", when(col("disliked_count").isNotNull && col("disliked_count") >= 0, col("disliked_count")).otherwise(0))

      // 5. 字段统一
      cleanedDF = cleanedDF
        .withColumn("raw_id", col("video_id").cast("long"))
        .withColumn("platform", lit("bilibili"))
        .withColumn("title_clean", DataCleanerUtils.cleanTitle(col("title")))
        .withColumn("content_clean", DataCleanerUtils.cleanContent(col("desc")))
        .withColumn("view_count", col("video_play_count").cast("int"))
        .withColumn("like_count", col("liked_count").cast("int"))
        .withColumn("coin_count", col("video_coin_count").cast("int"))
        .withColumn("favorite_count", col("video_favorite_count").cast("int"))
        .withColumn("share_count", col("video_share_count").cast("int"))
        .withColumn("comment_count", col("video_comment").cast("int"))
        .withColumn("publish_time", DataCleanerUtils.standardizeTime(col("create_time")))
        .withColumn("keyword", col("source_keyword"))

      // 6. 文本标准化
      cleanedDF = cleanedDF
        .filter(length(col("title_clean")) >= 5)
        .filter(length(col("content_clean")) >= 5)

      // 7. 计算发布时长（小时）
      cleanedDF = cleanedDF
        .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)

      // 8. 热度计算
      cleanedDF = DataCleanerUtils.calculateHotScore(cleanedDF)

      // 9. 选择最终字段
      val finalDF = cleanedDF.select(
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

      // 存储到MariaDB - 使用手动JDBC插入以避免SQL语法问题
      finalDF.foreachPartition { iterator: Iterator[org.apache.spark.sql.Row] =>
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

      logger.info(s"Processed ${finalDF.count()} video records with complete cleaning pipeline")

    } catch {
      case e: Exception =>
        logger.error("Error processing video data", e)
    }
  }

  /**
   * 处理评论数据 - 完整的数据清洗流程
   */
  def processCommentData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      logger.info("Starting comment data cleaning process...")
      logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")

      // 检查数据格式
      if (!df.columns.contains("comment_id")) {
        logger.error("DataFrame does not contain comment_id column, skipping processing")
        return
      }

      // 检查是否有数据
      if (df.isEmpty) {
        logger.info("No comment data to process")
        return
      }

      // 1. 数据读取与预处理
      var cleanedDF = df.filter(col("comment_id").isNotNull)

      // 2. 去重处理
      cleanedDF = cleanedDF.dropDuplicates("comment_id")

      // 3. 空值过滤
      cleanedDF = cleanedDF
        .filter(col("content").isNotNull && col("content") =!= "")
        .filter(col("video_id").isNotNull)
        .filter(col("user_id").isNotNull)

      // 4. 异常值清洗
      cleanedDF = cleanedDF
        .withColumn("like_count", when(col("like_count").isNotNull && col("like_count") >= 0, col("like_count")).otherwise(0))

      // 5. 字段统一
      cleanedDF = cleanedDF
        .withColumn("raw_id", col("comment_id").cast("long"))
        .withColumn("platform", lit("bilibili"))
        .withColumn("title_clean", lit(""))
        .withColumn("content_clean", DataCleanerUtils.cleanContent(col("content")))
        .withColumn("view_count", lit(0))
        .withColumn("like_count", col("like_count").cast("int"))
        .withColumn("coin_count", lit(0))
        .withColumn("favorite_count", lit(0))
        .withColumn("share_count", lit(0))
        .withColumn("comment_count", lit(1))
        .withColumn("publish_time", DataCleanerUtils.standardizeTime(col("create_time")))
        .withColumn("keyword", col("source_keyword"))

      // 6. 文本标准化
      cleanedDF = cleanedDF
        .filter(length(col("content_clean")) >= 5)

      // 7. 计算发布时长（小时）
      cleanedDF = cleanedDF
        .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)

      // 8. 热度计算
      cleanedDF = DataCleanerUtils.calculateHotScore(cleanedDF)

      // 9. 选择最终字段
      val finalDF = cleanedDF.select(
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

      // 存储到MariaDB - 使用手动JDBC插入以避免SQL语法问题
      finalDF.foreachPartition { iterator: Iterator[org.apache.spark.sql.Row] =>
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

      logger.info(s"Processed ${finalDF.count()} comment records with complete cleaning pipeline")

    } catch {
      case e: Exception =>
        logger.error("Error processing comment data", e)
    }
  }

  /**
   * 使用DataCleanerUtils中的方法进行数据清洗
   */
}
