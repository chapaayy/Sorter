-- Verify serialized embeddings as well as their content/model key.
ALTER TABLE reference_cache ADD COLUMN vector_sha256 TEXT CHECK(vector_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE reference_cache ADD COLUMN dimensions INTEGER CHECK(dimensions BETWEEN 1 AND 1000000);
