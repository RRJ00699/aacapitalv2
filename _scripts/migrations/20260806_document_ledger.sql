-- PR B: additive metadata for immutable contract-v1 R2 documents.
-- Apply the ALTER statements in a transaction, then run CREATE INDEX
-- CONCURRENTLY outside any transaction block.
ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS object_key TEXT,
    ADD COLUMN IF NOT EXISTS byte_size BIGINT,
    ADD COLUMN IF NOT EXISTS content_type TEXT,
    ADD COLUMN IF NOT EXISTS object_contract_version TEXT;

ALTER TABLE public.documents
    ADD CONSTRAINT documents_byte_size_positive_ck
        CHECK (byte_size IS NULL OR byte_size > 0) NOT VALID,
    ADD CONSTRAINT documents_content_type_pdf_ck
        CHECK (content_type IS NULL OR content_type = 'application/pdf') NOT VALID,
    ADD CONSTRAINT documents_object_contract_version_ck
        CHECK (object_contract_version IS NULL OR object_contract_version = '1') NOT VALID;

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS documents_ipo_type_sha_uq
    ON public.documents (ipo_id, doc_type, sha256)
    WHERE sha256 IS NOT NULL;
