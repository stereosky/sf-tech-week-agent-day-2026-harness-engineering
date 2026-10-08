"""Create the workshop topics and produce the five payments. Safe to run again.

python -m harness.seed           create what is missing
python -m harness.seed --reset   delete both topics and start again
"""

import sys

from harness import kafka_log, settings

PAYMENTS = [
    {"order_id": "ord_a1", "amount": 19.99, "currency": "GBP", "merchant": "Pret"},
    {"order_id": "ord_b7", "amount": 4.50, "currency": "GBP", "merchant": "Tesco"},
    {"order_id": "ord_c2", "amount": -8.00, "currency": "GBP", "merchant": "Costa"},
    {"order_id": "ord_d9", "amount": 120.00, "currency": "GBP", "merchant": "Waitrose"},
    {"order_id": "ord_e4", "amount": 7.25, "currency": "GBP", "merchant": "Boots"},
]


def main(reset: bool = False) -> None:
    kafka_log.wait_until_ready()
    if reset:
        kafka_log.delete_topics([settings.SESSION_TOPIC, settings.PAYMENTS_TOPIC])
        print(f"deleted {settings.SESSION_TOPIC} and {settings.PAYMENTS_TOPIC}")

    kafka_log.ensure_topic(settings.PAYMENTS_TOPIC)
    # Kafka deletes records after 7 days by default. The session log keeps everything.
    kafka_log.ensure_topic(settings.SESSION_TOPIC, {"retention.ms": "-1", "cleanup.policy": "delete"})

    if kafka_log.end_offset(settings.PAYMENTS_TOPIC) == 0:
        for payment in PAYMENTS:
            kafka_log.append(settings.PAYMENTS_TOPIC, payment["order_id"], payment)
        print(f"produced {len(PAYMENTS)} payments to {settings.PAYMENTS_TOPIC}")
    print(f"{settings.PAYMENTS_TOPIC}: {kafka_log.end_offset(settings.PAYMENTS_TOPIC)} records")
    print(f"{settings.SESSION_TOPIC}: {kafka_log.end_offset(settings.SESSION_TOPIC)} events")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv)
