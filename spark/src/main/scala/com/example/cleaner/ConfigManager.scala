package com.example.cleaner

import com.typesafe.config.ConfigFactory
import org.apache.spark.broadcast.Broadcast
import org.apache.spark.SparkContext

/**
 * 配置管理类
 * 用于读取和管理应用的配置信息
 */
object ConfigManager {
  private val config = ConfigFactory.load()

  // Kafka配置
  object Kafka {
    val bootstrapServers = config.getString("kafka.bootstrap.servers")

    object Bili {
      val topics = config.getStringList("kafka.bili.topics")
      val groupId = config.getString("kafka.bili.group.id")
    }

    object Nga {
      object Context {
        val topics = config.getStringList("kafka.nga.context.topics")
        val groupId = config.getString("kafka.nga.context.group.id")
      }
      
      object Comment {
        val topics = config.getStringList("kafka.nga.comment.topics")
        val groupId = config.getString("kafka.nga.comment.group.id")
      }
    }

    object Consumer {
      val autoOffsetReset = config.getString("kafka.consumer.auto.offset.reset")
      val enableAutoCommit = config.getBoolean("kafka.consumer.enable.auto.commit")
    }
    
    // 统一Kafka主题配置
    val unifiedTopic = config.getString("kafka.unified.topic")
    val unifiedGroupId = config.getString("kafka.unified.group.id")
  }

  // MySQL配置
  object MySQL {
    val url = config.getString("mysql.url")
    val user = config.getString("mysql.user")
    val password = config.getString("mysql.password")

    object Standardized {
      val database = config.getString("mysql.standardized.database")
      val fullUrl = config.getString("mysql.standardized.fullUrl")
      val table = config.getString("mysql.standardized.table")
    }
    
    // 数据库连接池配置
    val maxConnections = config.getInt("mysql.pool.maxConnections")
    val connectionTimeout = config.getInt("mysql.pool.connectionTimeout")
    val batchSize = config.getInt("mysql.batch.size")
    val retryTimes = config.getInt("mysql.retry.times")
  }

  // Spark配置
  object Spark {
    val appName = config.getString("spark.appName")
    val master = config.getString("spark.master")

    object Executor {
      val memory = config.getString("spark.executor.memory")
      val cores = config.getInt("spark.executor.cores")
    }

    object Driver {
      val memory = config.getString("spark.driver.memory")
    }

    object Streaming {
      val batchDuration = config.getInt("spark.streaming.batchDuration")
      val checkpointDir = config.getString("spark.streaming.checkpointDir")
    }
  }

  // 日志配置
  object Log {
    val level = config.getString("log.level")
    val pattern = config.getString("log.pattern")
  }
  
  // 归一化配置文件路径
  val normConfigPath = config.getString("norm.config.path")
}
