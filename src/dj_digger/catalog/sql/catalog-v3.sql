ALTER TABLE embedded_metadata ADD COLUMN input_size_bytes INTEGER NULL;
ALTER TABLE embedded_metadata ADD COLUMN input_mtime_ns INTEGER NULL;
ALTER TABLE embedded_metadata ADD COLUMN normalization_version TEXT NULL;
