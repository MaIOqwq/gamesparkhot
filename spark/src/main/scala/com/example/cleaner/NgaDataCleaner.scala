package com.example.cleaner

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.streaming._
import org.apache.spark.streaming.kafka010._
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.logging.log4j.LogManager
import scala.collection.Iterator

/**
 * NGA数据清洗类
 * 实现完整的数据清洗流程：去重、空值过滤、异常值清洗、字段统一、文本标准化、热度计算
 */
object NgaDataCleaner {
  private val logger = LogManager.getLogger(getClass)

  // 热度计算权重
  private val W2 = 1.5  // 评论权重

  def main(args: Array[String]): Unit = {
    logger.info("Starting NgaDataCleaner...")

    // 启动Kafka到Spark的传输
    KafkaToSparkTransmitter.startTransmission(
      appName = ConfigManager.Spark.appName,
      master = ConfigManager.Spark.master,
      batchDuration = ConfigManager.Spark.Streaming.batchDuration,
      kafkaDStreamCreator = KafkaToSparkTransmitter.createNgaKafkaDStream,
      messageProcessor = processNgaData
    )
  }

  /**
   * 处理NGA数据的消息处理器
   */
  private def processNgaData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    logger.info(s"Received NGA data batch with ${df.count()} records")
    logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")
    
    // 检查是否有数据
    if (df.isEmpty) {
      logger.info("No NGA data to process")
      return
    }
    
    // 检查数据结构
    if (df.columns.contains("data")) {
      logger.info("Data contains nested 'data' field, extracting data...")
      
      // 先检查数据类型：帖子数据（thread）或评论数据（content）
      val sampleData = df.select("data").limit(1)
      if (!sampleData.isEmpty) {
        // 检查data字段的结构
        val dataRow = sampleData.first().getAs[org.apache.spark.sql.Row]("data")
        val dataSchema = dataRow.schema
        logger.info(s"Data schema fields: ${dataSchema.fieldNames.mkString(", ")}")
        
        // 判断是帖子数据还是评论数据
        if (dataSchema.fieldNames.contains("title") && dataSchema.fieldNames.contains("replies")) {
          logger.info("Detected thread data (contains title and replies)")
          // 提取帖子数据
          val threadDF = df.select(
            "data.author",
            "data.post_date",
            "data.replies",
            "data.thread_id",
            "data.title",
            "data.url",
            "keyword",
            "timestamp",
            "type"
          )
          logger.info(s"Extracted ${threadDF.count()} thread records")
          logger.info(s"Thread columns: ${threadDF.columns.mkString(", ")}")
          
          val validThreadDF = threadDF.filter(col("thread_id").isNotNull)
          if (!validThreadDF.isEmpty) {
            logger.info(s"Processing ${validThreadDF.count()} valid thread records")
            processThreadData(validThreadDF, spark)
          }
          
        } else if (dataSchema.fieldNames.contains("content") && dataSchema.fieldNames.contains("author")) {
          logger.info("Detected content data (contains content and author)")
          // 提取评论数据
          val contentDF = df.select(
            "data.author",
            "data.content",
            "data.post_date",
            "data.thread_id",
            "data.type",
            "keyword",
            "timestamp"
          )
          logger.info(s"Extracted ${contentDF.count()} content records")
          logger.info(s"Content columns: ${contentDF.columns.mkString(", ")}")
          
          val validContentDF = contentDF.filter(col("content").isNotNull)
          if (!validContentDF.isEmpty) {
            logger.info(s"Processing ${validContentDF.count()} valid content records")
            processContentData(validContentDF, spark)
          }
          
        } else {
          logger.warn("Unknown data type, trying to extract all fields")
          val extractedDF = df.select("data.*", "keyword", "timestamp", "type")
          logger.info(s"Extracted ${extractedDF.count()} records")
          logger.info(s"Columns: ${extractedDF.columns.mkString(", ")}")
          
          // 尝试处理帖子数据
          if (extractedDF.columns.contains("thread_id") && extractedDF.columns.contains("title")) {
            val threadDF = extractedDF.filter(col("thread_id").isNotNull)
            if (!threadDF.isEmpty) {
              logger.info(s"Processing ${threadDF.count()} thread records")
              processThreadData(threadDF, spark)
            }
          }
          
          // 尝试处理评论数据
          if (extractedDF.columns.contains("content") && extractedDF.columns.contains("author")) {
            val contentDF = extractedDF.filter(col("content").isNotNull)
            if (!contentDF.isEmpty) {
              logger.info(s"Processing ${contentDF.count()} content records")
              processContentData(contentDF, spark)
            }
          }
        }
      }
      
    } else {
      logger.info("Data does not contain 'data' field, processing directly...")
      
      // 处理帖子基本信息（包含thread_id的帖子数据）
      if (df.columns.contains("thread_id") && df.columns.contains("title")) {
        val threadDF = df.filter(col("thread_id").isNotNull)
        if (!threadDF.isEmpty) {
          logger.info(s"Processing ${threadDF.count()} thread records")
          processThreadData(threadDF, spark)
        } else {
          logger.info("No thread data found (thread_id is null)")
        }
      } else {
        logger.info("No thread data found (missing thread_id or title column)")
      }
      
      // 处理帖子内容（包含content字段的内容数据）
      if (df.columns.contains("content") && df.columns.contains("author")) {
        val contentDF = df.filter(col("content").isNotNull)
        if (!contentDF.isEmpty) {
          logger.info(s"Processing ${contentDF.count()} content records")
          processContentData(contentDF, spark)
        } else {
          logger.info("No content data found (content is null)")
        }
      } else {
        logger.info("No content data found (missing content or author column)")
      }
    }
  }

  /**
   * 处理帖子基本信息 - 完整的数据清洗流程
   */
  private def processThreadData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      logger.info("Starting thread data cleaning process...")
      logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")

      // 检查数据格式
      if (!df.columns.contains("thread_id")) {
        logger.error("DataFrame does not contain thread_id column, skipping processing")
        return
      }

      // 检查是否有数据
      if (df.isEmpty) {
        logger.info("No thread data to process")
        return
      }

      // 1. 数据读取与预处理
      var cleanedDF = df.filter(col("thread_id").isNotNull)

      // 2. 去重处理
      cleanedDF = cleanedDF.dropDuplicates("thread_id")
      logger.info(s"After deduplication: ${cleanedDF.count()} records")

      // 3. 空值过滤 - Context数据（帖子）：只过滤title和thread_id为空的数据
      cleanedDF = cleanedDF
        .filter(col("thread_id").isNotNull && col("thread_id") =!= "")
        .filter(col("title").isNotNull && col("title") =!= "")
        .filter(col("author").isNotNull && col("author") =!= "")
        .filter(col("url").isNotNull && col("url") =!= "")
      logger.info(s"After null filtering: ${cleanedDF.count()} records")

      // 4. 异常值清洗
      cleanedDF = cleanedDF
        .withColumn("replies", when(col("replies").isNotNull && col("replies") >= 0, col("replies")).otherwise(0))

      // 5. 字段统一
      cleanedDF = cleanedDF
        .withColumn("raw_id", col("thread_id").cast("long"))
        .withColumn("platform", lit("nga"))
        .withColumn("title_clean", DataCleanerUtils.cleanTitle(col("title")))
        .withColumn("content_clean", lit(""))
        .withColumn("view_count", lit(0))
        .withColumn("like_count", lit(0))
        .withColumn("coin_count", lit(0))
        .withColumn("favorite_count", lit(0))
        .withColumn("share_count", lit(0))
        .withColumn("comment_count", when(col("replies").isNotNull, col("replies").cast("int")).otherwise(0))
        .withColumn("publish_time", when(col("timestamp").isNotNull,
            DataCleanerUtils.standardizeTime(col("timestamp"))
          ).otherwise(
            DataCleanerUtils.standardizeTime(col("post_date"))
          ))
        .withColumn("keyword", col("keyword"))

      // 6. 文本标准化
      cleanedDF = cleanedDF
        .filter(length(col("title_clean")) >= 5)
      logger.info(s"After text standardization: ${cleanedDF.count()} records")

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

      logger.info(s"Final thread records to output: ${finalDF.count()}")
      logger.info(s"Processed ${finalDF.count()} thread records with complete cleaning pipeline")

    } catch {
      case e: Exception =>
        logger.error("Error processing thread data", e)
    }
  }

  /**
   * 处理帖子内容 - 完整的数据清洗流程
   */
  private def processContentData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      logger.info("Starting content data cleaning process...")
      logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")

      // 检查数据格式
      if (!df.columns.contains("thread_id")) {
        logger.error("DataFrame does not contain thread_id column, skipping processing")
        return
      }

      // 检查是否有数据
      if (df.isEmpty) {
        logger.info("No content data to process")
        return
      }

      // 1. 数据读取与预处理
      var cleanedDF = df.filter(col("thread_id").isNotNull)
      logger.info(s"After preprocessing: ${cleanedDF.count()} records")

      // 2. 去重处理
      cleanedDF = cleanedDF.dropDuplicates()
      logger.info(s"After deduplication: ${cleanedDF.count()} records")

      // 3. 空值过滤 - Comment数据（评论）：只过滤thread_id、author和content为空的数据
      cleanedDF = cleanedDF
        .filter(col("thread_id").isNotNull && col("thread_id") =!= "")
        .filter(col("content").isNotNull && col("content") =!= "")
        .filter(col("author").isNotNull && col("author") =!= "")
      logger.info(s"After null filtering: ${cleanedDF.count()} records")

      // 4. 异常值清洗
      cleanedDF = cleanedDF
        .filter(col("type").isin("main", "reply"))
      logger.info(s"After type filtering: ${cleanedDF.count()} records")

      // 5. 字段统一
      cleanedDF = cleanedDF
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
        .withColumn("publish_time", when(col("timestamp").isNotNull,
            DataCleanerUtils.standardizeTime(col("timestamp"))
          ).otherwise(current_timestamp()))
        .withColumn("keyword", col("keyword"))

      // 6. 文本标准化
      cleanedDF = cleanedDF
        .filter(length(col("content_clean")) >= 5)

      // 7. 计算发布时长（小时）
      cleanedDF = cleanedDF
        .withColumn("time_diff", lit(0.0))

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

      logger.info(s"Processed ${finalDF.count()} content records with complete cleaning pipeline")

    } catch {
      case e: Exception =>
        logger.error("Error processing content data", e)
    }
  }

  /**
   * 使用DataCleanerUtils中的方法进行数据清洗
   */
}
