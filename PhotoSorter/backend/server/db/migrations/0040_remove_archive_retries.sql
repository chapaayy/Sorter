-- Archives are HTTP-only temporary objects; no durable retry queue.
DROP TABLE IF EXISTS archive_retries;
