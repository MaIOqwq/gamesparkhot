package com.example.cleaner

import org.apache.spark.sql.{SparkSession, DataFrame, Row, Column}
import org.apache.spark.sql.functions._
import org.apache.spark.sql.types._
import org.apache.spark.streaming._
import org.apache.spark.streaming.dstream.InputDStream
import org.apache.spark.streaming.kafka010._
import org.apache.kafka.clients.consumer.ConsumerRecord
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.logging.log4j.LogManager
import scala.collection.Iterator
import java.sql.{Connection, DriverManager, PreparedStatement, Timestamp}
import scala.io.Source
import org.json.JSONObject
import java.net.{HttpURLConnection, URL}
import java.io.{BufferedReader, InputStreamReader, OutputStreamWriter}

/**
 * 情感分析服务客户端
 */
class SentimentServiceClient(serviceUrl: String) {
  private val logger = LogManager.getLogger(classOf[SentimentServiceClient])
  
  /**
   * 调用情感分析服务
   */
  def getSentimentScore(text: String): Float = {
    if (text == null || text.isEmpty) {
      return 0.0f
    }
    
    val url = new URL(s"$serviceUrl/sentiment")
    val conn = url.openConnection().asInstanceOf[HttpURLConnection]
    
    try {
      conn.setRequestMethod("POST")
      conn.setRequestProperty("Content-Type", "application/json")
      conn.setDoOutput(true)
      
      val requestBody = s"""{"text": "${text.replace("\"", "\\\"")}"}"""
      
      val writer = new OutputStreamWriter(conn.getOutputStream)
      writer.write(requestBody)
      writer.flush()
      writer.close()
      
      val responseCode = conn.getResponseCode
      
      if (responseCode == HttpURLConnection.HTTP_OK) {
        val reader = new BufferedReader(new InputStreamReader(conn.getInputStream, "UTF-8"))
        val response = reader.lines().toArray.mkString("\n")
        reader.close()
        
        logger.debug(s"Received sentiment response: $response")
        
        try {
          val json = new JSONObject(response)
          val score = json.getDouble("sentiment_score").toFloat
          logger.info(s"Sentiment analysis successful: score = $score")
          score
        } catch {
          case e: Exception =>
            logger.error(s"JSON解析失败: ${e.getMessage}, Response: $response")
            0.0f
        }
      } else {
        logger.warn(s"情感分析服务返回错误状态码: $responseCode")
        0.0f
      }
    } catch {
      case e: Exception =>
        logger.error(s"调用情感分析服务失败: ${e.getMessage}")
        0.0f
    } finally {
      conn.disconnect()
    }
  }
}

/**
 * 统一数据清洗类
 * 处理NGA和Bilibili的数据，进行清洗、字段映射、热度计算，最终写入MySQL
 */
object UnifiedDataCleaner {
  private val logger = LogManager.getLogger(getClass)
  private val sentimentServiceUrl = "http://localhost:8001"
  private val sentimentClient = new SentimentServiceClient(sentimentServiceUrl)
  
  def main(args: Array[String]): Unit = {
    logger.info("Starting UnifiedDataCleaner...")
    
    // 启动Kafka到Spark的传输
    KafkaToSparkTransmitter.startTransmission(
      appName = ConfigManager.Spark.appName,
      master = ConfigManager.Spark.master,
      batchDuration = ConfigManager.Spark.Streaming.batchDuration,
      kafkaDStreamCreator = createUnifiedKafkaDStream,
      messageProcessor = processUnifiedData
    )
  }
  
  /**
   * 创建统一Kafka DStream
   */
  def createUnifiedKafkaDStream(ssc: StreamingContext): InputDStream[ConsumerRecord[String, String]] = {
    val kafkaParams = Map[String, Object](
      "bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
      "key.deserializer" -> classOf[StringDeserializer],
      "value.deserializer" -> classOf[StringDeserializer],
      "group.id" -> ConfigManager.Kafka.unifiedGroupId,
      "auto.offset.reset" -> ConfigManager.Kafka.Consumer.autoOffsetReset,
      "enable.auto.commit" -> (ConfigManager.Kafka.Consumer.enableAutoCommit: java.lang.Boolean)
    )
    
    val topics = scala.Array(ConfigManager.Kafka.unifiedTopic)
    KafkaToSparkTransmitter.createKafkaDStream(ssc, kafkaParams, topics)
  }
  
  /**
   * 处理统一数据
   */
  private def processUnifiedData(df: DataFrame, spark: SparkSession): Unit = {
    logger.info(s"Received unified data batch with ${df.count()} records")
    
    if (df.isEmpty) {
      logger.info("No data to process")
      return
    }
    
    // 1. 消息解析与基础校验
    val validDF = df.filter(col("platform").isNotNull && col("raw_id").isNotNull && 
                          col("author").isNotNull && col("publish_time").isNotNull && 
                          col("keyword").isNotNull)
    
    if (validDF.isEmpty) {
      logger.warn("No valid data after basic validation")
      return
    }
    
    // 2. 文本清洗
    val cleanedDF = validDF
      .withColumn("title_clean", cleanText(col("title")))
      .withColumn("content_clean", cleanText(col("content")))
    
    // 3. 时间标准化
    val timeStandardizedDF = cleanedDF
      .withColumn("publish_time", to_timestamp(col("publish_time"), "yyyy-MM-dd HH:mm:ss"))
      .filter(col("publish_time").isNotNull)
    
    if (timeStandardizedDF.isEmpty) {
      logger.warn("No data after time standardization")
      return
    }
    
    // 4. 字段映射与默认值填充
    val mappedDF = timeStandardizedDF
      .withColumn("platform", when(col("platform") === "bilibili", 1).when(col("platform") === "nga", 0).otherwise(0))
      .withColumn("type", when(col("type").isNull, "unknown").otherwise(col("type")))
      .withColumn("view_count", when(col("view_count").isNotNull && col("view_count") >= 0, col("view_count")).otherwise(0))
      .withColumn("like_count", when(col("like_count").isNotNull && col("like_count") >= 0, col("like_count")).otherwise(0))
      .withColumn("comment_count", when(col("comment_count").isNotNull && col("comment_count") >= 0, col("comment_count")).otherwise(0))
      .withColumn("coin_count", when(col("coin_count").isNotNull && col("coin_count") >= 0, col("coin_count")).otherwise(0))
      .withColumn("favorite_count", when(col("favorite_count").isNotNull && col("favorite_count") >= 0, col("favorite_count")).otherwise(0))
      .withColumn("share_count", when(col("share_count").isNotNull && col("share_count") >= 0, col("share_count")).otherwise(0))
      .withColumn("danmaku_count", when(col("danmaku_count").isNotNull && col("danmaku_count") >= 0, col("danmaku_count")).otherwise(0))
      .withColumn("is_hot_reply", when(col("is_hot_reply") === true, 1).otherwise(0))
      .withColumn("author_fans", when(col("author_fans").isNotNull && col("author_fans") >= 0, col("author_fans")).otherwise(0))
      .withColumn("author_level", when(col("author_level").isNotNull && col("author_level") >= 0, col("author_level")).otherwise(0))
      .withColumn("author_post_count", when(col("author_post_count").isNotNull && col("author_post_count") >= 0, col("author_post_count")).otherwise(0))
      .withColumn("has_image", when(col("has_image") === true, 1).otherwise(0))
      .withColumn("has_video", when(col("has_video") === true, 1).otherwise(0))
      .withColumn("board_name", when(col("board_name").isNull, "").otherwise(col("board_name")))
    
    // 5. 计算热度值：等权求和 + log(1+x) + 固定P95归一化
    val hotScoreDF = mappedDF.withColumn("hot_raw",
      col("like_count") + col("comment_count") +
      col("coin_count") + col("favorite_count") + col("share_count")
    ).withColumn("hot_log", log1p(col("hot_raw")))
     .withColumn("hot_norm",
      when(col("platform") === 1,
        least(col("hot_log") / 11.2932, lit(1.0)))
      .when(col("platform") === 0,
        least(col("hot_log") / 3.2581, lit(1.0)))
      .otherwise(0.0)
    ).withColumn("hot_score", col("hot_norm"))
    
    // 8. 文本长度 text_length
    val withTextLengthDF = hotScoreDF
      .withColumn("text_length", when(col("content_clean").isNull, 0).otherwise(length(col("content_clean"))))
    
    // 9. 调用情感分析服务获取情感得分
    val sentimentUDF = udf((content: String) => {
      sentimentClient.getSentimentScore(content)
    })
    
    val finalDF = withTextLengthDF
      .withColumn("sentiment_score", sentimentUDF(col("content_clean")))
    
    // 9. 选择最终字段
    val outputDF = finalDF.select(
      col("raw_id"),
      col("platform"),
      col("type"),
      col("author"),
      col("title_clean"),
      col("content_clean"),
      col("publish_time"),
      col("keyword"),
      col("view_count"),
      col("like_count"),
      col("comment_count"),
      col("coin_count"),
      col("favorite_count"),
      col("share_count"),
      col("danmaku_count"),
      col("is_hot_reply"),
      col("author_fans"),
      col("author_level"),
      col("author_post_count"),
      col("has_image"),
      col("has_video"),
      col("board_name"),
      col("hot_raw"),
      col("hot_norm"),
      col("hot_score"),
      col("text_length"),
      col("sentiment_score")
    )
    
    // 10. 写入数据库 + 回访队列
    writeToDatabase(outputDF)
    writeToCrawlQueue(outputDF, spark)

    logger.info(s"Processed ${outputDF.count()} records")
  }
  
  /**
   * 文本清洗函数
   */
  private def cleanText(text: Column): Column = {
    var cleaned = text.cast("string")
    cleaned = regexp_replace(cleaned, "\\+Rby\\[.*?\\]\\(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}\\)", "")
    cleaned = regexp_replace(cleaned, "<[^>]+>", "")
    cleaned = regexp_replace(cleaned, "https?://\\S+", "")
    cleaned = regexp_replace(cleaned, "[^\\u4e00-\\u9fa5a-zA-Z0-9\\.,!\\?;:\\(\\)\\[\\]\\{\\}]", "")
    cleaned = regexp_replace(cleaned, "\\s+", " ")
    cleaned = trim(cleaned)
    
    when(cleaned === "", null).otherwise(cleaned)
  }
  
  /**
   * 加载归一化配置
   */
  /**
   * 写入数据库
   */
  private def writeToDatabase(df: DataFrame): Unit = {
    df.foreachPartition { iterator: Iterator[Row] =>
      if (iterator.nonEmpty) {
        var conn: Connection = null
        var stmt: PreparedStatement = null
        var retryCount = 0
        
        while (retryCount < ConfigManager.MySQL.retryTimes) {
          try {
            Class.forName("org.mariadb.jdbc.Driver")
            conn = DriverManager.getConnection(
              s"${ConfigManager.MySQL.Standardized.fullUrl}?useSSL=false&useUnicode=true&characterEncoding=utf8mb4",
              ConfigManager.MySQL.user,
              ConfigManager.MySQL.password
            )
            
            val sql = """INSERT INTO standardized_data 
                        |(raw_id, platform, type, author, title_clean, content_clean, publish_time, keyword,
                        |view_count, like_count, comment_count, coin_count, favorite_count, share_count,
                        |danmaku_count, is_hot_reply, author_fans, author_level, author_post_count,
                        |has_image, has_video, board_name, hot_raw, hot_norm, hot_score, text_length, sentiment_score)
                        |VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        |ON DUPLICATE KEY UPDATE
                        |type = VALUES(type),
                        |author = VALUES(author),
                        |title_clean = VALUES(title_clean),
                        |content_clean = VALUES(content_clean),
                        |publish_time = VALUES(publish_time),
                        |keyword = VALUES(keyword),
                        |view_count = VALUES(view_count),
                        |like_count = VALUES(like_count),
                        |comment_count = VALUES(comment_count),
                        |coin_count = VALUES(coin_count),
                        |favorite_count = VALUES(favorite_count),
                        |share_count = VALUES(share_count),
                        |danmaku_count = VALUES(danmaku_count),
                        |is_hot_reply = VALUES(is_hot_reply),
                        |author_fans = VALUES(author_fans),
                        |author_level = VALUES(author_level),
                        |author_post_count = VALUES(author_post_count),
                        |has_image = VALUES(has_image),
                        |has_video = VALUES(has_video),
                        |board_name = VALUES(board_name),
                        |hot_raw = VALUES(hot_raw),
                        |hot_norm = VALUES(hot_norm),
                        |hot_score = VALUES(hot_score),
                        |text_length = VALUES(text_length),
                        |sentiment_score = VALUES(sentiment_score)""".stripMargin
            
            stmt = conn.prepareStatement(sql)
            
            iterator.grouped(ConfigManager.MySQL.batchSize).foreach { batch =>
              batch.foreach { row =>
                // 安全的类型转换方法
                def toInt(value: Any): Int = value match {
                  case i: Int => i
                  case l: Long => l.toInt
                  case d: Double => d.toInt
                  case s: String => try { s.toInt } catch { case _: Exception => 0 }
                  case _ => 0
                }
                
                def toDouble(value: Any): Double = value match {
                  case d: Double => d
                  case i: Int => i.toDouble
                  case l: Long => l.toDouble
                  case s: String => try { s.toDouble } catch { case _: Exception => 0.0 }
                  case _ => 0.0
                }
                
                def toString(value: Any): String = value match {
                  case s: String => s
                  case l: Long => l.toString
                  case i: Int => i.toString
                  case d: Double => d.toString
                  case f: Float => f.toString
                  case _ => ""
                }
                
                def toFloat(value: Any): Float = value match {
                  case f: Float => f
                  case d: Double => d.toFloat
                  case i: Int => i.toFloat
                  case l: Long => l.toFloat
                  case s: String => try { s.toFloat } catch { case _: Exception => 0.0f }
                  case _ => 0.0f
                }
                
                stmt.setString(1, toString(row.getAs[Any]("raw_id")))
                stmt.setInt(2, toInt(row.getAs[Any]("platform")))
                stmt.setString(3, toString(row.getAs[Any]("type")))
                stmt.setString(4, toString(row.getAs[Any]("author")))
                stmt.setString(5, toString(row.getAs[Any]("title_clean")))
                stmt.setString(6, toString(row.getAs[Any]("content_clean")))
                stmt.setTimestamp(7, row.getAs[java.sql.Timestamp]("publish_time"))
                stmt.setString(8, toString(row.getAs[Any]("keyword")))
                stmt.setInt(9, toInt(row.getAs[Any]("view_count")))
                stmt.setInt(10, toInt(row.getAs[Any]("like_count")))
                stmt.setInt(11, toInt(row.getAs[Any]("comment_count")))
                stmt.setInt(12, toInt(row.getAs[Any]("coin_count")))
                stmt.setInt(13, toInt(row.getAs[Any]("favorite_count")))
                stmt.setInt(14, toInt(row.getAs[Any]("share_count")))
                stmt.setInt(15, toInt(row.getAs[Any]("danmaku_count")))
                stmt.setInt(16, toInt(row.getAs[Any]("is_hot_reply")))
                stmt.setInt(17, toInt(row.getAs[Any]("author_fans")))
                stmt.setInt(18, toInt(row.getAs[Any]("author_level")))
                stmt.setInt(19, toInt(row.getAs[Any]("author_post_count")))
                stmt.setInt(20, toInt(row.getAs[Any]("has_image")))
                stmt.setInt(21, toInt(row.getAs[Any]("has_video")))
                stmt.setString(22, toString(row.getAs[Any]("board_name")))
                stmt.setDouble(23, toDouble(row.getAs[Any]("hot_raw")))
                stmt.setDouble(24, toDouble(row.getAs[Any]("hot_norm")))
                stmt.setDouble(25, toDouble(row.getAs[Any]("hot_score")))
                stmt.setInt(26, toInt(row.getAs[Any]("text_length")))
                stmt.setFloat(27, toFloat(row.getAs[Any]("sentiment_score")))
                stmt.addBatch()
              }
              stmt.executeBatch()
            }
            
            logger.info("Successfully wrote batch to database")
            retryCount = ConfigManager.MySQL.retryTimes
            
          } catch {
            case e: Exception =>
              retryCount += 1
              logger.error(s"Error writing to database, retry $retryCount/${ConfigManager.MySQL.retryTimes}", e)
              if (retryCount >= ConfigManager.MySQL.retryTimes) {
                logger.error("Failed to write to database after all retries")
              }
          } finally {
            if (stmt != null) stmt.close()
            if (conn != null) conn.close()
          }
        }
      }
    }
  }

  /**
   * 写入爬虫回访队列（首次爬取时 INSERT，已存在则跳过）
   */
  private def writeToCrawlQueue(df: DataFrame, spark: SparkSession): Unit = {
    import spark.implicits._

    // 有些爬虫不发送 _crawl_type 字段（如 NGA），此时也视为首次爬取
    val hasCrawlType = df.columns.contains("_crawl_type")
    val firstDF = if (hasCrawlType) {
      df.filter(col("_crawl_type").isNull || col("_crawl_type") === "first")
    } else {
      df
    }
    if (firstDF.isEmpty) return

    firstDF.foreachPartition { iterator: Iterator[Row] =>
      // Cache rows to list since iterator can only be consumed once
      val rows = iterator.toList
      if (rows.nonEmpty) {
        var conn: Connection = null
        var stmt: PreparedStatement = null
        try {
          Class.forName("org.mariadb.jdbc.Driver")
          conn = DriverManager.getConnection(
            s"${ConfigManager.MySQL.Standardized.fullUrl}?useSSL=false&useUnicode=true&characterEncoding=utf8mb4",
            ConfigManager.MySQL.user,
            ConfigManager.MySQL.password
          )

          // 1) Write to crawl_queue (first capture only, IGNORE duplicates)
          val cqSql = """INSERT IGNORE INTO crawl_queue
                      |(raw_id, platform, url, keyword, first_captured, last_visited, next_visit,
                      | current_lambda, revisit_level, last_comment_count, last_hot_raw, status, visit_count)
                      |VALUES (?, ?, ?, ?, NOW(), NOW(), DATE_ADD(NOW(), INTERVAL 1 HOUR),
                      | 0.0, 0, ?, ?, 'active', 1)""".stripMargin
          stmt = conn.prepareStatement(cqSql)
          rows.foreach { row =>
            val rawId = Option(row.getAs[Any]("raw_id")).map(_.toString).getOrElse("")
            val platform = row.getAs[Any]("platform") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val keyword = Option(row.getAs[Any]("keyword")).map(_.toString).getOrElse("")
            val commentCount = row.getAs[Any]("comment_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val hotRaw = row.getAs[Any]("hot_raw") match { case d: Double => d; case f: Float => f.toDouble; case i: Int => i.toDouble; case _ => 0.0 }
            stmt.setString(1, rawId)
            stmt.setInt(2, platform)
            stmt.setString(3, "")
            stmt.setString(4, keyword)
            stmt.setInt(5, commentCount)
            stmt.setDouble(6, hotRaw)
            stmt.addBatch()
          }
          stmt.executeBatch()
          logger.info(s"Successfully wrote ${rows.size} rows to crawl_queue")

          // 2) Write initial capture to content_metrics
          stmt.close()
          val cmSql = """INSERT INTO content_metrics
                      |(raw_id, platform, captured_at, comment_count, like_count,
                      | coin_count, favorite_count, share_count, view_count,
                      | hot_raw, hot_score, lambda, revisit_level)
                      |VALUES (?, ?, NOW(), ?, ?, ?, ?, ?, ?, ?, 0.0, 0, 0)""".stripMargin
          stmt = conn.prepareStatement(cmSql)
          rows.foreach { row =>
            val rawId = Option(row.getAs[Any]("raw_id")).map(_.toString).getOrElse("")
            val platform = row.getAs[Any]("platform") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val commentCount = row.getAs[Any]("comment_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val likeCount = row.getAs[Any]("like_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val coinCount = row.getAs[Any]("coin_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val favCount = row.getAs[Any]("favorite_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val shareCount = row.getAs[Any]("share_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val viewCount = row.getAs[Any]("view_count") match { case i: Int => i; case l: Long => l.toInt; case _ => 0 }
            val hotRaw = row.getAs[Any]("hot_raw") match { case d: Double => d; case f: Float => f.toDouble; case i: Int => i.toDouble; case _ => 0.0 }
            stmt.setString(1, rawId)
            stmt.setInt(2, platform)
            stmt.setInt(3, commentCount)
            stmt.setInt(4, likeCount)
            stmt.setInt(5, coinCount)
            stmt.setInt(6, favCount)
            stmt.setInt(7, shareCount)
            stmt.setInt(8, viewCount)
            stmt.setDouble(9, hotRaw)
            stmt.addBatch()
          }
          stmt.executeBatch()
          logger.info(s"Successfully wrote ${rows.size} rows to content_metrics")
        } catch {
          case e: Exception =>
            logger.error(s"Error writing to crawl_queue/content_metrics: ${e.getMessage}")
        } finally {
          if (stmt != null) stmt.close()
          if (conn != null) conn.close()
        }
      }
    }
  }
}
