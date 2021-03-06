from pyspark.sql import SparkSession
from pyspark.sql.functions import to_date, concat_ws, col, expr, size, collect_list, udf, from_unixtime, window, to_timestamp, sum, array_distinct, explode
from pyspark.sql.types import IntegerType
import datetime
import os
from lib.logger import Log4j

if __name__ == "__main__":

    AWS_KEY = os.environ['AWS_ACCESS_KEY_ID']
    AWS_SECRET_KEY = os.environ['AWS_SECRET_ACCESS_KEY']

    spark = SparkSession \
        .builder \
        .appName("TikTok Static Test") \
        .master("local[3]") \
        .config("fs.s3a.access.key", AWS_KEY) \
        .config("fs.s3a.secret.key", AWS_SECRET_KEY) \
        .config('spark.driver.extraClassPath', '/Users/beccaboo/postgresql-42.2.18.jar') \
        .config('spark.executor.extraClassPath', '/Users/beccaboo/postgresql-42.2.18.jar') \
        .getOrCreate()

        #logger = Log4j(spark)

    now = datetime.datetime.now().date()
    #now_date = now.strftime("%Y-%m-%d")
    yesterdate = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    #Read raw streaming data from S3
    json_df = spark.read \
        .parquet("s3a://tiktokstreamingproject/rawkafka/2021-01-05/*")


    filtered_df = json_df \
        .selectExpr("value.authorInfos.uniqueId",
                    "value.authorInfos.userId",
                    "value.challengeInfoList.challengeId",
                    "value.challengeInfoList.challengeName",
                    "value.challengeInfoList.isCommerce",
                    "value.itemInfos.commentCount",
                    "value.itemInfos.diggCount",
                    "value.itemInfos.id",
                    "value.itemInfos.isActivityItem",
                    "value.itemInfos.shareCount",
                    "value.itemInfos.text",
                    "value.musicInfos.authorName",
                    "value.musicInfos.musicId",
                    "value.musicInfos.musicName",
                    "value.time_stamp") \
        .withColumn("engagementCount", expr("commentCount + diggCount + shareCount")) \
        .withColumn("challengeId", concat_ws('', 'challengeId')) \
        .withColumn("challengeName", concat_ws('', 'challengeName')) \
        .withColumn("isCommerce", concat_ws('', 'isCommerce').cast("boolean")) \
        .withColumn("date", to_date(to_timestamp(from_unixtime(col("time_stamp").cast(IntegerType()), "yyyy-MM-dd HH:mm:ss"),
                                          "yyyy-MM-dd HH:mm:ss"))) \
        .withColumnRenamed("authorName", "musicianName")


    #Write codes to push to table
    filtered_df.write.format("jdbc").mode("append") \
    .option("url", "jdbc:postgresql://localhost/tiktok") \
    .option("dbtable", "tiktok_filtered") \
    .save()

    #create wordcount table, Read data from filtered_df table
    wordcount_df = filtered_df \
        .select(col("date"), col("id"), explode(array_distinct(expr("split(text, ' ')"))).alias("words")) \
        .groupBy(col("date"), col("words")) \
        .agg(collect_list(col("id")).alias("ids")) \
        .withColumn("TotalMentions", size(col("ids"))) \
        .drop("ids")

    #Save to wordcount table
    wordcount_df.write.format("jdbc").mode("append") \
    .option("url", "jdbc:postgresql://localhost/tiktok") \
    .option("dbtable", "wordcount") \
    .save()

    #Challenge Table
    challenge_df = filtered_df \
        .groupBy(col("date"), col("challengeName")) \
        .agg(sum(col("engagementCount")).alias("TotalEngagement")) \
        .orderBy(col("TotalEngagement").desc())

    #Save to challenge table
    challenge_df.write.format("jdbc").mode("append") \
    .option("url", "jdbc:postgresql://localhost/tiktok") \
    .option("dbtable", "challenge") \
    .save()
    # #Author Table
    # author_df = filtered_df \
    #     .groupBy(col("date"), col("userId")) \
    #     .agg(sum(col("engagementCount")).alias("TotalEngagement")) \
    #     .orderBy(col("TotalEngagement").desc())
    #
    # #Music Table
    # music_df = filtered_df \
    #     .groupBy(col("date"), col("musicId")) \
    #     .agg(sum(col("engagementCount")).alias("TotalEngagement")) \
    #     .orderBy(col("TotalEngagement").desc())
    #
    # #Musician Table
    # musician_df = filtered_df \
    #     .groupBy(col("date"), col("musicianName")) \
    #     .agg(sum(col("engagementCount")).alias("TotalEngagement")) \
    #     .orderBy(col("TotalEngagement").desc())
    #Write code to push all tables to database/redshift end of day
