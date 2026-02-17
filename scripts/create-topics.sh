#!/usr/bin/env bash
# Create NornWeave Kafka topics.
# Usage: ./scripts/create-topics.sh [KAFKA_BOOTSTRAP]

set -euo pipefail

KAFKA_BROKER="${1:-${KAFKA_BOOTSTRAP:-localhost:9092}}"

echo "Creating topics on ${KAFKA_BROKER}..."

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create --if-not-exists \
  --topic nornweave.ingestion.events \
  --partitions 4 --replication-factor 1 \
  --config retention.ms=604800000 --config cleanup.policy=delete

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create --if-not-exists \
  --topic nornweave.agent.lifecycle \
  --partitions 1 --replication-factor 1 \
  --config retention.ms=259200000 --config cleanup.policy=delete

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create --if-not-exists \
  --topic nornweave.routing.feedback \
  --partitions 4 --replication-factor 1 \
  --config retention.ms=604800000 --config cleanup.policy=delete

kafka-topics.sh --bootstrap-server "$KAFKA_BROKER" --create --if-not-exists \
  --topic nornweave.dlq \
  --partitions 1 --replication-factor 1 \
  --config retention.ms=2592000000 --config cleanup.policy=delete

echo "Done."
