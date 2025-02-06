from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, round, to_json, struct
from pyspark.sql.types import *

# Initialize SparkSession
spark = SparkSession.builder \
    .appName("TestKafka") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0") \
    .getOrCreate()

# Read data from Kafka (update with your Kafka settings)
# in bootstrap server option, broker is the container name in which kafka is running
df = spark \
    .readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker:9092") \
    .option("subscribe", "test-topic") \
    .option('startingOffsets', 'earliest')\
    .load()

# Process the streaming data
value_df = df.selectExpr("CAST(value AS STRING)")

## Input Schema
df_schema = StructType([
    StructField("transaction_id", StringType(), True),
    StructField("customer_id", StringType(), True),
    StructField("timestamp", TimestampType(), True),
    StructField("product_id", StringType(), True),
    StructField("amount", IntegerType(), True),
    StructField("merchant_id", StringType(), True)
])

json_df = value_df.withColumn('value_json', from_json(col('value'), df_schema))\
                .selectExpr('value_json.*')

eligible_df = json_df.filter((col('amount') > 500) & 
                             (col('merchant_id').isin('merch_1', 'merch_3'))) \
                     .withColumn('cashback', round(col('amount').cast('double') * 0.15, 2)) \
                     .select(col("customer_id"),col("amount"),col("cashback"),col("merchant_id"),col("timestamp"))

## Create an output 
# Kafka takes only string. And the clm name should be value
# converting the df into json string with clm name as 'value'

output_df = eligible_df.select(to_json(struct(*eligible_df.columns)).alias("value"))

# writing into kafka topic
# output_df.writeStream \
#     .format("kafka") \
#     .outputMode("append") \
#     .option("kafka.bootstrap.servers", "broker:9092") \
#     .option("topic", "eligible_cutomers_topic") \
#     .option("checkpointLocation", "./kafka_checkpoints") \
#     .start() \
#     .awaitTermination()

# writing as a parquet
# eligible_df.writeStream \
#     .format("parquet") \
#     .outputMode("append") \
#     .option("path", "./parquet_output") \
#     .option("checkpointLocation", "./kafka_checkpoints") \
#     .start() \
#     .awaitTermination()


# Define a function to write each batch to PostgreSQL
def write_to_postgres(batch_df, batch_id):
    batch_df.write \
        .format("jdbc") \
        .option("url", "jdbc:postgresql://postgres_db:5432/cashback_db") \
        .option("dbtable", "eligible_customers") \
        .option("user", "postgres") \
        .option("password",  "postgres123") \
        .option("driver", "org.postgresql.Driver") \
        .mode("append") \
        .save()

# Apply foreachBatch for micro-batch writes
query = eligible_df.writeStream \
    .outputMode("append") \
    .foreachBatch(write_to_postgres) \
    .option("checkpointLocation", "/path/to/checkpoints") \
    .start()

query.awaitTermination()