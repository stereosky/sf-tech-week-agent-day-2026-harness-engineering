"""Kafka plumbing the harness owns: the session log, the seed data and the verifier's reads.

Every topic in this workshop has one partition, so offset order is event order.
"""

import json
import time

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from harness import settings

_producer: Producer | None = None


def _config(**extra) -> dict:
    return {"bootstrap.servers": settings.KAFKA_BOOTSTRAP, **extra}


def _get_producer() -> Producer:
    global _producer
    if _producer is None:
        # librdkafka defaults idempotence to off; on means no duplicates or reordering on retry.
        _producer = Producer(_config(**{"enable.idempotence": True, "linger.ms": 0, "client.id": "harness"}))
    return _producer


def append(topic: str, key: str, value: dict) -> int:
    """Write-ahead append. Returns only once Kafka has acknowledged the record, with its offset."""
    delivery: dict = {}

    def delivered(err, msg):
        delivery["error"] = err
        delivery["offset"] = None if err else msg.offset()

    producer = _get_producer()
    producer.produce(topic, key=key, value=json.dumps(value, sort_keys=True), on_delivery=delivered)
    producer.flush(10)
    if delivery.get("error") or delivery.get("offset") is None:
        raise KafkaException(delivery.get("error") or f"{topic}: record was not acknowledged")
    return delivery["offset"]


def read(topic: str, key: str | None = None, start: int = 0) -> list[dict]:
    """Every record from `start` to the end of the topic as {key, offset, value}, optionally for one key.

    No consumer group state: assign, read to the end-of-partition marker, close.
    """
    consumer = Consumer(
        _config(
            **{
                "group.id": "harness-reader",  # required by the client, never committed
                "enable.auto.commit": False,
                "enable.partition.eof": True,
                "fetch.wait.max.ms": 10,  # the default of 500 ms makes every read take half a second
            }
        )
    )
    try:
        metadata = consumer.list_topics(topic, timeout=10).topics.get(topic)
        if metadata is None or metadata.error is not None:
            return []
        assignments, waiting = [], set()
        for partition in metadata.partitions:
            low, high = consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=10)
            if high > max(low, start):
                assignments.append(TopicPartition(topic, partition, max(low, start)))
                waiting.add(partition)
        if not assignments:
            return []
        consumer.assign(assignments)
        records = []
        while waiting:
            msg = consumer.poll(10.0)
            if msg is None:
                raise TimeoutError(f"{topic}: did not reach the end of the partition")
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    waiting.discard(msg.partition())
                    continue
                raise KafkaException(msg.error())
            record_key = msg.key().decode() if msg.key() else None
            if key is None or record_key == key:
                records.append({"key": record_key, "offset": msg.offset(), "value": _decode(msg.value())})
        return records
    finally:
        consumer.close()


def _decode(raw: bytes | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"_raw": raw.decode(errors="replace")}


def end_offset(topic: str) -> int:
    """High watermark summed over partitions: the number of records ever written to the topic."""
    consumer = Consumer(_config(**{"group.id": "harness-reader"}))
    try:
        metadata = consumer.list_topics(topic, timeout=10).topics.get(topic)
        if metadata is None or metadata.error is not None:
            return 0
        return sum(consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1] for p in metadata.partitions)
    finally:
        consumer.close()


def wait_until_ready(timeout: float = 180) -> None:
    # log_level 0 hides the "connection refused" noise while the broker is still starting.
    admin, deadline = AdminClient(_config(log_level=0)), time.monotonic() + timeout
    while True:
        try:
            admin.list_topics(timeout=5)
            return
        except KafkaException:
            if time.monotonic() > deadline:
                raise
            time.sleep(2)


def ensure_topic(name: str, config: dict | None = None) -> bool:
    """Create a single-partition topic if it is missing. Returns True if it was created."""
    admin = AdminClient(_config())
    deadline = time.monotonic() + 60
    while name not in admin.list_topics(timeout=10).topics:
        future = admin.create_topics([NewTopic(name, num_partitions=1, replication_factor=1, config=config or {})])
        try:
            future[name].result()
            return True
        except KafkaException as exc:
            if "already exists" in str(exc).lower() and "marked for deletion" not in str(exc).lower():
                return False
            if time.monotonic() > deadline:
                raise
            time.sleep(2)
    return False


def delete_topics(names: list[str]) -> None:
    admin = AdminClient(_config())
    existing = [n for n in names if n in admin.list_topics(timeout=10).topics]
    for future in admin.delete_topics(existing).values() if existing else []:
        future.result()
    deadline = time.monotonic() + 60
    while any(n in admin.list_topics(timeout=10).topics for n in existing):
        if time.monotonic() > deadline:
            raise TimeoutError(f"topics still exist after delete: {existing}")
        time.sleep(1)
