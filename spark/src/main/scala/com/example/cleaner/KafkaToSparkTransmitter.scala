package com.example.cleaner

import org.apache.spark.sql.SparkSession
import org.apache.spark.streaming._
import org.apache.spark.streaming.dstream.InputDStream
import org.apache.spark.streaming.kafka010._
import org.apache.spark.streaming.kafka010.ConsumerStrategies.Subscribe
import org.apache.spark.streaming.kafka010.LocationStrategies.PreferConsistent
import org.apache.kafka.clients.consumer.ConsumerRecord
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.logging.log4j.LogManager
import scala.collection.JavaConverters._

/**
 * Kafka到Spark的传输类
 * 负责从Kafka读取数据并传输到Spark进行处理
 */
object KafkaToSparkTransmitter {
  private val logger = LogManager.getLogger(getClass)

  /**
   * 创建Kafka DStream
   * @param ssc StreamingContext
   * @param kafkaParams Kafka配置参数
   * @param topics 要订阅的主题
   * @return Kafka DStream
   */
  def createKafkaDStream(
      ssc: StreamingContext,
      kafkaParams: Map[String, Object],
      topics: Array[String]
  ): InputDStream[ConsumerRecord[String, String]] = {
    logger.info(s"Creating Kafka DStream for topics: ${topics.mkString(", ")}")
    
    // 创建Kafka DStream
    val stream = KafkaUtils.createDirectStream[String, String](
      ssc,
      PreferConsistent,
      Subscribe[String, String](topics, kafkaParams)
    )
    
    logger.info("Kafka DStream created successfully")
    stream
  }

  /**
   * 为B站数据创建Kafka DStream
   * @param ssc StreamingContext
   * @return B站数据的Kafka DStream
   */
  def createBiliKafkaDStream(ssc: StreamingContext): InputDStream[ConsumerRecord[String, String]] = {
    // B站Kafka配置
    val kafkaParams = Map[String, Object](
      "bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
      "key.deserializer" -> classOf[StringDeserializer],
      "value.deserializer" -> classOf[StringDeserializer],
      "group.id" -> ConfigManager.Kafka.Bili.groupId,
      "auto.offset.reset" -> ConfigManager.Kafka.Consumer.autoOffsetReset,
      "enable.auto.commit" -> (ConfigManager.Kafka.Consumer.enableAutoCommit: java.lang.Boolean)
    )
    
    // B站主题
    val topics = ConfigManager.Kafka.Bili.topics.asScala.toArray
    
    createKafkaDStream(ssc, kafkaParams, topics)
  }

  /**
   * 为NGA帖子数据创建Kafka DStream
   * @param ssc StreamingContext
   * @return NGA帖子数据的Kafka DStream
   */
  def createNgaContextKafkaDStream(ssc: StreamingContext): InputDStream[ConsumerRecord[String, String]] = {
    // NGA帖子Kafka配置
    val kafkaParams = Map[String, Object](
      "bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
      "key.deserializer" -> classOf[StringDeserializer],
      "value.deserializer" -> classOf[StringDeserializer],
      "group.id" -> ConfigManager.Kafka.Nga.Context.groupId,
      "auto.offset.reset" -> ConfigManager.Kafka.Consumer.autoOffsetReset,
      "enable.auto.commit" -> (ConfigManager.Kafka.Consumer.enableAutoCommit: java.lang.Boolean)
    )
    
    // NGA帖子主题
    val topics = ConfigManager.Kafka.Nga.Context.topics.asScala.toArray
    
    createKafkaDStream(ssc, kafkaParams, topics)
  }
  
  /**
   * 为NGA评论数据创建Kafka DStream
   * @param ssc StreamingContext
   * @return NGA评论数据的Kafka DStream
   */
  def createNgaCommentKafkaDStream(ssc: StreamingContext): InputDStream[ConsumerRecord[String, String]] = {
    // NGA评论Kafka配置
    val kafkaParams = Map[String, Object](
      "bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
      "key.deserializer" -> classOf[StringDeserializer],
      "value.deserializer" -> classOf[StringDeserializer],
      "group.id" -> ConfigManager.Kafka.Nga.Comment.groupId,
      "auto.offset.reset" -> ConfigManager.Kafka.Consumer.autoOffsetReset,
      "enable.auto.commit" -> (ConfigManager.Kafka.Consumer.enableAutoCommit: java.lang.Boolean)
    )
    
    // NGA评论主题
    val topics = ConfigManager.Kafka.Nga.Comment.topics.asScala.toArray
    
    createKafkaDStream(ssc, kafkaParams, topics)
  }
  
  /**
   * 为NGA数据创建Kafka DStream（同时订阅context和comment两个topic）
   * @param ssc StreamingContext
   * @return NGA数据的Kafka DStream
   */
  def createNgaKafkaDStream(ssc: StreamingContext): InputDStream[ConsumerRecord[String, String]] = {
    // NGA Kafka配置
    val kafkaParams = Map[String, Object](
      "bootstrap.servers" -> ConfigManager.Kafka.bootstrapServers,
      "key.deserializer" -> classOf[StringDeserializer],
      "value.deserializer" -> classOf[StringDeserializer],
      "group.id" -> "nga-cleaner-group",
      "auto.offset.reset" -> ConfigManager.Kafka.Consumer.autoOffsetReset,
      "enable.auto.commit" -> (ConfigManager.Kafka.Consumer.enableAutoCommit: java.lang.Boolean)
    )
    
    // NGA主题（同时订阅context和comment）
    val contextTopics = ConfigManager.Kafka.Nga.Context.topics.asScala.toArray
    val commentTopics = ConfigManager.Kafka.Nga.Comment.topics.asScala.toArray
    val topics = contextTopics ++ commentTopics
    
    logger.info(s"Subscribing to NGA topics: ${topics.mkString(", ")}")
    createKafkaDStream(ssc, kafkaParams, topics)
  }

  /**
   * 处理Kafka消息
   * @param stream Kafka DStream
   * @param spark SparkSession
   * @param processor 消息处理器
   */
  def processKafkaMessages(
      stream: InputDStream[ConsumerRecord[String, String]],
      spark: SparkSession,
      processor: (org.apache.spark.sql.DataFrame, SparkSession) => Unit
  ): Unit = {
    stream.foreachRDD { rdd =>
      if (!rdd.isEmpty()) {
        logger.info(s"Processing batch with ${rdd.count()} records")
        
        try {
          // 将RDD转换为DataFrame
          val df = spark.read.json(rdd.map(_.value))
          
          // 调用处理器处理数据
          processor(df, spark)
          
        } catch {
          case e: Exception =>
            logger.error("Error processing Kafka messages", e)
            throw e
        }
      }
    }
  }

  /**
   * 启动Kafka到Spark的传输
   * @param appName 应用名称
   * @param master Spark master
   * @param batchDuration 批处理间隔（秒）
   * @param kafkaDStreamCreator Kafka DStream创建器
   * @param messageProcessor 消息处理器
   */
  def startTransmission(
      appName: String,
      master: String,
      batchDuration: Int,
      kafkaDStreamCreator: StreamingContext => InputDStream[ConsumerRecord[String, String]],
      messageProcessor: (org.apache.spark.sql.DataFrame, SparkSession) => Unit
  ): Unit = {
    logger.info(s"Starting Kafka to Spark transmission for $appName")
    
    // 创建SparkSession
    val spark = SparkSession.builder()
      .appName(appName)
      .master(master)
      .config("spark.executor.memory", ConfigManager.Spark.Executor.memory)
      .config("spark.executor.cores", ConfigManager.Spark.Executor.cores)
      .config("spark.driver.memory", ConfigManager.Spark.Driver.memory)
      .config("spark.sql.dialect", "mysql")
      .getOrCreate()
    
    // 创建StreamingContext
    val ssc = new StreamingContext(spark.sparkContext, Seconds(batchDuration))
    // 设置检查点目录
    ssc.checkpoint(ConfigManager.Spark.Streaming.checkpointDir)
    
    try {
      // 创建Kafka DStream
      val stream = kafkaDStreamCreator(ssc)
      
      // 处理消息
      processKafkaMessages(stream, spark, messageProcessor)
      
      // 启动流处理
      ssc.start()
      logger.info(s"$appName started successfully")
      ssc.awaitTermination()
      
    } catch {
      case e: Exception =>
        logger.error(s"Error in $appName", e)
        throw e
    } finally {
      ssc.stop(stopSparkContext = true, stopGracefully = true)
      logger.info(s"$appName stopped")
    }
  }
}
