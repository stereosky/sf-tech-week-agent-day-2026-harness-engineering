# How to investigate this Kafka cluster

- Find topics with `list_topics`. Pass part of a topic name, or an empty string to see every topic.
- Read records with `execute_sql`, which runs Lenses SQL. Start with `SELECT * FROM payments LIMIT 20` so you see every field. Never guess field names.
- Read every record before you decide. The answer comes from comparing records with each other.
- Report what you found. Never try to change or repair data.
