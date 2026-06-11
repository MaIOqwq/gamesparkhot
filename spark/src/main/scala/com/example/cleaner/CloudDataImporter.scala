package com.example.cleaner

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.logging.log4j.LogManager

/**
 * 云端数据导入类
 * 用于导入云端服务器上的爬虫数据并进行清洗
 */
object CloudDataImporter {
  private val logger = LogManager.getLogger(getClass)

  def main(args: Array[String]): Unit = {
    println("Starting CloudDataImporter...")
    logger.info("Starting CloudDataImporter...")

    // 创建SparkSession
    val spark = SparkSession.builder()
      .appName("CloudDataImporter")
      .master("local[*]")
      .config("spark.sql.dialect", "mysql")
      .getOrCreate()

    println("SparkSession created successfully")
    logger.info("SparkSession created successfully")

    try {
      // 导入NGA数据
      importNgaData(spark)
      
      // 导入B站数据
      importBiliData(spark)

    } catch {
      case e: Exception =>
        println(s"Error in CloudDataImporter: ${e.getMessage}")
        e.printStackTrace()
        logger.error("Error in CloudDataImporter", e)
    } finally {
      spark.stop()
      println("CloudDataImporter stopped")
      logger.info("CloudDataImporter stopped")
    }
  }

  /**
   * 导入NGA数据
   */
  private def importNgaData(spark: SparkSession): Unit = {
    println("Importing NGA data...")
    logger.info("Importing NGA data...")
    
    // 读取NGA数据文件 - 只处理comment和context目录下的JSON文件
    val ngaContextDf = spark.read.option("multiline", "true").json("/data/NGA/*/context/*.json")
      .withColumn("input_file", input_file_name())
      .withColumn("keyword", regexp_replace(element_at(split(col("input_file"), "/"), -1), "\\.json$", ""))
    
    val ngaCommentDf = spark.read.option("multiline", "true").json("/data/NGA/*/comment/*.json")
      .withColumn("input_file", input_file_name())
      .withColumn("keyword", regexp_replace(element_at(split(col("input_file"), "/"), -1), "\\.json$", ""))
    
    val contextCount = ngaContextDf.count()
    val commentCount = ngaCommentDf.count()
    
    println(s"Read $contextCount context records from NGA")
    println(s"Read $commentCount comment records from NGA")
    logger.info(s"Read $contextCount context records from NGA")
    logger.info(s"Read $commentCount comment records from NGA")
    
    // 直接导入NGA数据到数据库，跳过清洗工作流
    if (!ngaContextDf.isEmpty) {
      println("Importing NGA context data directly to database...")
      importNgaDataToDatabase(ngaContextDf, spark, "nga")
    } else {
      println("No NGA context data to process")
    }
    
    if (!ngaCommentDf.isEmpty) {
      println("Importing NGA comment data directly to database...")
      importNgaDataToDatabase(ngaCommentDf, spark, "nga")
    } else {
      println("No NGA comment data to process")
    }
    
    println("NGA data imported and cleaned successfully")
    logger.info("NGA data imported and cleaned successfully")
  }

  /**
   * 导入B站数据
   */
  private def importBiliData(spark: SparkSession): Unit = {
    println("Importing Bili data...")
    logger.info("Importing Bili data...")
    
    // 读取B站数据文件 - 只处理comment和context目录下的JSON文件
    val biliContextDf = spark.read.option("multiline", "true").json("/data/bili/*/context/*.json")
      .withColumn("input_file", input_file_name())
      .withColumn("source_keyword", regexp_replace(element_at(split(col("input_file"), "/"), -1), "\\.json$", ""))
    
    val biliCommentDf = spark.read.option("multiline", "true").json("/data/bili/*/comment/*.json")
      .withColumn("input_file", input_file_name())
      .withColumn("source_keyword", regexp_replace(element_at(split(col("input_file"), "/"), -1), "\\.json$", ""))
    
    val contextCount = biliContextDf.count()
    val commentCount = biliCommentDf.count()
    
    println(s"Read $contextCount context records from Bili")
    println(s"Read $commentCount comment records from Bili")
    logger.info(s"Read $contextCount context records from Bili")
    logger.info(s"Read $commentCount comment records from Bili")
    
    // 直接导入B站数据到数据库，跳过清洗工作流
    if (!biliContextDf.isEmpty) {
      println("Importing Bili context data directly to database...")
      importBiliDataToDatabase(biliContextDf, spark, "bilibili")
    } else {
      println("No Bili context data to process")
    }
    
    if (!biliCommentDf.isEmpty) {
      println("Importing Bili comment data directly to database...")
      importBiliDataToDatabase(biliCommentDf, spark, "bilibili")
    } else {
      println("No Bili comment data to process")
    }
    
    println("Bili data imported successfully")
    logger.info("Bili data imported successfully")
  }

  /**
   * 直接将NGA数据导入数据库
   */
  private def importNgaDataToDatabase(df: org.apache.spark.sql.DataFrame, spark: SparkSession, platform: String): Unit = {
    import spark.implicits._
    
    // 转换为标准化格式
    val standardizedDF = df
      .withColumn("raw_id", col("thread_id").cast("long"))
      .withColumn("platform", lit(platform))
      .withColumn("title_clean", when(col("title").isNotNull, col("title")).otherwise(""))
      .withColumn("content_clean", when(col("content").isNotNull, col("content")).otherwise(""))
      .withColumn("view_count", lit(0))
      .withColumn("like_count", lit(0))
      .withColumn("coin_count", lit(0))
      .withColumn("favorite_count", lit(0))
      .withColumn("share_count", lit(0))
      .withColumn("comment_count", when(col("replies").isNotNull, col("replies").cast("int")).otherwise(0))
      .withColumn("publish_time", when(col("timestamp").isNotNull, 
          from_unixtime(col("timestamp").cast("long"))
        ).otherwise(
          when(col("post_date").isNotNull && col("post_date") =!= "",
            to_timestamp(col("post_date"), "MM-dd HH:mm")
          ).otherwise(current_timestamp())
        ))
      .withColumn("time_diff", lit(0.0))
      .withColumn("hot_raw", lit(1.0))
      .withColumn("hot_norm", lit(0.0))
      .withColumn("hot_score", lit(0.0))
      .withColumn("keyword", col("keyword"))

    // 选择最终字段
    val finalDF = standardizedDF.select(
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

    // 存储到数据库
    finalDF.foreachPartition { (iter: Iterator[org.apache.spark.sql.Row]) =>
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
        iter.foreach { row =>
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
          val publishTime = row.getAs[java.sql.Timestamp]("publish_time")
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
          logger.error("Error writing NGA data to database", e)
          throw e
      } finally {
        if (stmt != null) stmt.close()
        if (conn != null) conn.close()
      }
    }
    
    println(s"Imported ${finalDF.count()} NGA records directly to database")
    logger.info(s"Imported ${finalDF.count()} NGA records directly to database")
  }

  /**
   * 直接将B站数据导入数据库
   */
  private def importBiliDataToDatabase(df: org.apache.spark.sql.DataFrame, spark: SparkSession, platform: String): Unit = {
    import spark.implicits._
    
    // 转换为标准化格式
    val standardizedDF = df
      .withColumn("raw_id", when(col("video_id").isNotNull, col("video_id").cast("long")).otherwise(col("comment_id").cast("long")))
      .withColumn("platform", lit(platform))
      .withColumn("title_clean", when(col("title").isNotNull, col("title")).otherwise(""))
      .withColumn("content_clean", when(col("desc").isNotNull, col("desc")).when(col("content").isNotNull, col("content")).otherwise(""))
      .withColumn("view_count", when(col("video_play_count").isNotNull, col("video_play_count").cast("int")).otherwise(0))
      .withColumn("like_count", when(col("liked_count").isNotNull, col("liked_count").cast("int")).when(col("like_count").isNotNull, col("like_count").cast("int")).otherwise(0))
      .withColumn("coin_count", when(col("video_coin_count").isNotNull, col("video_coin_count").cast("int")).otherwise(0))
      .withColumn("favorite_count", when(col("video_favorite_count").isNotNull, col("video_favorite_count").cast("int")).otherwise(0))
      .withColumn("share_count", when(col("video_share_count").isNotNull, col("video_share_count").cast("int")).otherwise(0))
      .withColumn("comment_count", when(col("video_comment").isNotNull, col("video_comment").cast("int")).otherwise(0))
      .withColumn("publish_time", when(col("create_time").isNotNull,
          from_unixtime(col("create_time").cast("long"))
        ).otherwise(current_timestamp()))
      .withColumn("time_diff", lit(0.0))
      .withColumn("hot_raw", lit(1.0))
      .withColumn("hot_norm", lit(0.0))
      .withColumn("hot_score", lit(0.0))
      .withColumn("keyword", col("source_keyword"))

    // 选择最终字段
    val finalDF = standardizedDF.select(
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

    // 存储到数据库
    finalDF.foreachPartition { (iter: Iterator[org.apache.spark.sql.Row]) =>
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
        iter.foreach { row =>
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
          val publishTime = row.getAs[java.sql.Timestamp]("publish_time")
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
          logger.error("Error writing Bili data to database", e)
          throw e
      } finally {
        if (stmt != null) stmt.close()
        if (conn != null) conn.close()
      }
    }
    
    println(s"Imported ${finalDF.count()} Bili records directly to database")
    logger.info(s"Imported ${finalDF.count()} Bili records directly to database")
  }
}