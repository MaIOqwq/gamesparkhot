package com.example.cleaner

import org.apache.spark.sql.SparkSession

object TestSpark {
  def main(args: Array[String]): Unit = {
    println("Starting TestSpark...")
    
    val spark = SparkSession.builder()
      .appName("TestSpark")
      .master("local[*]")
      .getOrCreate()
    
    println("SparkSession created successfully")
    
    // Test basic Spark functionality with multiline option for JSON arrays
    val df = spark.read.option("multiline", "true").json("file:///e:/bishe/data/bili/2026-03-20/context/原神.json")
    println(s"DataFrame columns: ${df.columns.mkString(", ")}")
    println(s"DataFrame count: ${df.count()}")
    df.show(5)
    
    spark.stop()
    println("TestSpark completed")
  }
}