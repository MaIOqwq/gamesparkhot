package com.example.cleaner

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.streaming._
import org.apache.spark.storage.StorageLevel
import org.apache.logging.log4j.LogManager
import scala.collection.Iterator

/**
 * B站数据清洗类 - 内存优化版本
 * 修复了内存泄漏和性能问题
 */
object MemoryOptimizedBiliDataCleaner {
  private val logger = LogManager.getLogger(getClass)

  // 热度计算权重
  private val W1 = 1.0
  private val W2 = 1.5
  private val W3 = 1.2

  def main(args: Array[String]): Unit = {
    logger.info("Starting MemoryOptimizedBiliDataCleaner...")
    
    // 添加JVM内存监控
    startMemoryMonitor()

    KafkaToSparkTransmitter.startTransmission(
      appName = "BiliDataCleaner-Optimized",
      master = ConfigManager.Spark.master,
      batchDuration = ConfigManager.Spark.Streaming.batchDuration,
      kafkaDStreamCreator = KafkaToSparkTransmitter.createBiliKafkaDStream,
      messageProcessor = processBiliData
    )
  }
  
  /**
   * 内存监控线程
   */
  private def startMemoryMonitor(): Unit = {
    val monitorThread = new Thread(new Runnable {
      def run(): Unit = {
        while (!Thread.currentThread().isInterrupted) {
          val runtime = Runtime.getRuntime
          val totalMemory = runtime.totalMemory() / 1024 / 1024
          val freeMemory = runtime.freeMemory() / 1024 / 1024
          val usedMemory = totalMemory - freeMemory
          val maxMemory = runtime.maxMemory() / 1024 / 1024
          
          logger.info(s"[Memory Monitor] Used: ${usedMemory}MB / ${maxMemory}MB (${(usedMemory.toDouble/maxMemory*100).formatted("%.1f")}%)")
          
          // 如果使用内存超过80%，建议GC
          if (usedMemory.toDouble / maxMemory > 0.8) {
            logger.warn("[Memory Monitor] Memory usage high, suggesting GC...")
            System.gc()
          }
          
          Thread.sleep(30000) // 每30秒监控一次
        }
      }
    })
    monitorThread.setDaemon(true)
    monitorThread.start()
  }

  /**
   * 处理B站数据的消息处理器 - 内存优化版本
   */
  private def processBiliData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    // 缓存原始DataFrame，避免重复计算
    df.persist(StorageLevel.MEMORY_AND_DISK_SER)
    
    try {
      val count = df.count()
      logger.info(s"Received Bili data batch with $count records")
      
      if (df.isEmpty) {
        logger.info("No Bili data to process")
        return
      }
      
      logger.info(s"Columns in DataFrame: ${df.columns.mkString(", ")}")
      
      // 检查数据结构
      if (df.columns.contains("data")) {
        processNestedData(df, spark)
      } else {
        processFlatData(df, spark)
      }
    } finally {
      // 确保释放缓存
      df.unpersist(blocking = false)
    }
  }
  
  /**
   * 处理嵌套数据结构
   */
  private def processNestedData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    logger.info("Data contains nested 'data' field, extracting data...")
    
    // 只取样1条数据检查结构，不触发完整计算
    val sampleData = df.select("data").limit(1)
    if (sampleData.isEmpty) {
      logger.warn("Sample data is empty")
      return
    }
    
    val dataRow = sampleData.first().getAs[org.apache.spark.sql.Row]("data")
    val dataSchema = dataRow.schema
    
    // 判断数据类型并处理
    if (dataSchema.fieldNames.contains("video_id") && dataSchema.fieldNames.contains("title")) {
      processVideoDataOptimized(df, spark)
    } else if (dataSchema.fieldNames.contains("comment_id") && dataSchema.fieldNames.contains("content")) {
      processCommentDataOptimized(df, spark)
    } else {
      logger.warn("Unknown data type, skipping processing")
    }
  }
  
  /**
   * 处理扁平数据结构
   */
  private def processFlatData(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    logger.info("Data does not contain 'data' field, processing directly...")
    
    if (df.columns.contains("video_id")) {
      val videoDF = df.filter(col("video_id").isNotNull)
      if (!videoDF.isEmpty) {
        processVideoDataOptimized(videoDF, spark)
      }
    }
    
    if (df.columns.contains("comment_id")) {
      val commentDF = df.filter(col("comment_id").isNotNull)
      if (!commentDF.isEmpty) {
        processCommentDataOptimized(commentDF, spark)
      }
    }
  }

  /**
   * 处理视频数据 - 内存优化版本
   */
  private def processVideoDataOptimized(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      logger.info("Starting video data cleaning process...")
      
      import spark.implicits._

      if (!df.columns.contains("video_id")) {
        logger.error("DataFrame does not contain video_id column")
        return
      }

      // 提取并缓存视频数据
      val videoDF = df.select(
        "data.video_id", "data.user_id", "data.liked_count", "data.title",
        "data.desc", "data.create_time", "data.disliked_count", "data.video_play_count",
        "data.video_favorite_count", "data.video_share_count", "data.video_coin_count",
        "data.video_danmaku", "data.video_comment", "source_keyword", "timestamp"
      ).filter(col("video_id").isNotNull)
      
      // 缓存中间结果
      videoDF.persist(StorageLevel.MEMORY_AND_DISK_SER)
      
      try {
        if (videoDF.isEmpty) {
          logger.info("No valid video data to process")
          return
        }
        
        logger.info(s"Processing video data...")

        // 数据清洗流程 - 链式操作，避免中间DataFrame
        val cleanedDF = videoDF
          .dropDuplicates("video_id")
          .filter(col("title").isNotNull && col("title") =!= "")
          .filter(col("source_keyword").isNotNull && col("source_keyword") =!= "")
          .withColumn("video_play_count", when(col("video_play_count").isNotNull && col("video_play_count") >= 0, col("video_play_count")).otherwise(0))
          .withColumn("video_favorite_count", when(col("video_favorite_count").isNotNull && col("video_favorite_count") >= 0, col("video_favorite_count")).otherwise(0))
          .withColumn("video_share_count", when(col("video_share_count").isNotNull && col("video_share_count") >= 0, col("video_share_count")).otherwise(0))
          .withColumn("video_coin_count", when(col("video_coin_count").isNotNull && col("video_coin_count") >= 0, col("video_coin_count")).otherwise(0))
          .withColumn("video_danmaku", when(col("video_danmaku").isNotNull && col("video_danmaku") >= 0, col("video_danmaku")).otherwise(0))
          .withColumn("video_comment", when(col("video_comment").isNotNull && col("video_comment") >= 0, col("video_comment")).otherwise(0))
          .withColumn("liked_count", when(col("liked_count").isNotNull && col("liked_count") >= 0, col("liked_count")).otherwise(0))
          .withColumn("disliked_count", when(col("disliked_count").isNotNull && col("disliked_count") >= 0, col("disliked_count")).otherwise(0))
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
          .filter(length(col("title_clean")) >= 5)
          .filter(length(col("content_clean")) >= 5)
          .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)
        
        // 热度计算
        val withHotScore = DataCleanerUtils.calculateHotScore(cleanedDF)
        
        // 选择最终字段
        val finalDF = withHotScore.select(
          col("raw_id"), col("platform"), col("title_clean"), col("content_clean"),
          col("view_count"), col("like_count"), col("coin_count"), col("favorite_count"),
          col("share_count"), col("comment_count"), col("publish_time"), col("time_diff"),
          col("hot_raw"), col("hot_norm"), col("hot_score"), col("keyword")
        )
        
        // 批量写入数据库
        saveToDatabaseOptimized(finalDF)
        
        logger.info("Video data processed successfully")
        
      } finally {
        videoDF.unpersist(blocking = false)
      }

    } catch {
      case e: Exception =>
        logger.error("Error processing video data", e)
    }
  }

  /**
   * 处理评论数据 - 内存优化版本
   */
  private def processCommentDataOptimized(df: org.apache.spark.sql.DataFrame, spark: SparkSession): Unit = {
    try {
      logger.info("Starting comment data cleaning process...")

      if (!df.columns.contains("comment_id")) {
        logger.error("DataFrame does not contain comment_id column")
        return
      }

      // 提取评论数据
      val commentDF = df.select(
        "data.user_id", "data.comment_id", "data.video_id", "data.content",
        "data.create_time", "data.like_count", "source_keyword", "timestamp"
      ).filter(col("comment_id").isNotNull)
      
      commentDF.persist(StorageLevel.MEMORY_AND_DISK_SER)
      
      try {
        if (commentDF.isEmpty) {
          logger.info("No valid comment data to process")
          return
        }

        // 链式处理
        val cleanedDF = commentDF
          .dropDuplicates("comment_id")
          .filter(col("content").isNotNull && col("content") =!= "")
          .filter(col("video_id").isNotNull)
          .filter(col("user_id").isNotNull)
          .withColumn("like_count", when(col("like_count").isNotNull && col("like_count") >= 0, col("like_count")).otherwise(0))
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
          .filter(length(col("content_clean")) >= 5)
          .withColumn("time_diff", (unix_timestamp(current_timestamp()) - unix_timestamp(col("publish_time"))) / 3600.0)
        
        val withHotScore = DataCleanerUtils.calculateHotScore(cleanedDF)
        
        val finalDF = withHotScore.select(
          col("raw_id"), col("platform"), col("title_clean"), col("content_clean"),
          col("view_count"), col("like_count"), col("coin_count"), col("favorite_count"),
          col("share_count"), col("comment_count"), col("publish_time"), col("time_diff"),
          col("hot_raw"), col("hot_norm"), col("hot_score"), col("keyword")
        )
        
        saveToDatabaseOptimized(finalDF)
        
        logger.info("Comment data processed successfully")
        
      } finally {
        commentDF.unpersist(blocking = false)
      }

    } catch {
      case e: Exception =>
        logger.error("Error processing comment data", e)
    }
  }

  /**
   * 优化的数据库写入方法 - 使用批量写入和连接池
   */
  private def saveToDatabaseOptimized(df: org.apache.spark.sql.DataFrame): Unit = {
    // 使用coalesce减少分区数，避免过多数据库连接
    val optimizedDF = df.coalesce(4)
    
    optimizedDF.foreachPartition { iterator: Iterator[org.apache.spark.sql.Row] =>
      import java.sql._
      var conn: Connection = null
      var stmt: PreparedStatement = null
      
      try {
        Class.forName("org.mariadb.jdbc.Driver")
        conn = DriverManager.getConnection(
          s"${ConfigManager.MySQL.Standardized.fullUrl}?useSSL=false&useUnicode=true&characterEncoding=utf8mb4&rewriteBatchedStatements=true&useServerPrepStmts=true",
          ConfigManager.MySQL.user,
          ConfigManager.MySQL.password
        )
        
        // 设置自动提交为false，使用批量提交
        conn.setAutoCommit(false)
        
        val sql = """
          INSERT INTO standardized_data 
          (raw_id, platform, title_clean, content_clean, view_count, like_count, coin_count, 
           favorite_count, share_count, comment_count, publish_time, time_diff, hot_raw, hot_norm, hot_score, keyword) 
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON DUPLICATE KEY UPDATE
          title_clean = VALUES(title_clean),
          content_clean = VALUES(content_clean),
          view_count = VALUES(view_count),
          like_count = VALUES(like_count),
          coin_count = VALUES(coin_count),
          favorite_count = VALUES(favorite_count),
          share_count = VALUES(share_count),
          comment_count = VALUES(comment_count),
          time_diff = VALUES(time_diff),
          hot_raw = VALUES(hot_raw),
          hot_norm = VALUES(hot_norm),
          hot_score = VALUES(hot_score)
        """
        
        stmt = conn.prepareStatement(sql)
        
        var batchCount = 0
        val batchSize = 1000 // 每1000条提交一次
        
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
          
          batchCount += 1
          
          // 达到批次大小时执行提交
          if (batchCount % batchSize == 0) {
            stmt.executeBatch()
            conn.commit()
            stmt.clearBatch()
          }
        }
        
        // 提交剩余的数据
        if (batchCount % batchSize != 0) {
          stmt.executeBatch()
          conn.commit()
        }
        
        logger.info(s"Successfully saved $batchCount records to database")
        
      } catch {
        case e: Exception =>
          logger.error("Error writing to database", e)
          if (conn != null) {
            try {
              conn.rollback()
            } catch {
              case rollbackEx: Exception =>
                logger.error("Error rolling back transaction", rollbackEx)
            }
          }
          throw e
      } finally {
        if (stmt != null) stmt.close()
        if (conn != null) conn.close()
      }
    }
  }
}
