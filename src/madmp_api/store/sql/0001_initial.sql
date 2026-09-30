-- Materialised maDMP projection (see madmp_api.store.models.MadmpRow).
-- {prefix} is replaced by the configured table prefix. IF NOT EXISTS keeps
-- the script safe on a store created before this migration runner.

CREATE TABLE IF NOT EXISTS {prefix}dmp (
    -- Wizard host the row belongs to; empty for a single Wizard.
    tenant text NOT NULL DEFAULT '',
    id text NOT NULL,
    id_base_url text NOT NULL DEFAULT '',
    wizard_project_uuid text NOT NULL,
    data jsonb NOT NULL,
    title text NOT NULL,
    description text,
    created timestamptz NOT NULL,
    modified timestamptz NOT NULL,
    language text NOT NULL,
    ethical_issues_exist text NOT NULL,
    wizard_updated_at timestamptz NOT NULL,
    search_text text NOT NULL DEFAULT '',
    dataset_ids text[] NOT NULL,
    contributor_ids text[] NOT NULL,
    contact_ids text[] NOT NULL,
    dmp_ids text[] NOT NULL,
    dmp_alternate_identifiers text[] NOT NULL,
    host_ids text[] NOT NULL,
    funder_ids text[] NOT NULL,
    grant_ids text[] NOT NULL,
    metadata_standard_ids text[] NOT NULL,
    license_refs text[] NOT NULL,
    distribution_formats text[] NOT NULL,
    distribution_data_access text[] NOT NULL,
    funding_status text[] NOT NULL,
    dataset_personal_data text[] NOT NULL,
    dataset_sensitive_data text[] NOT NULL,
    CONSTRAINT {prefix}dmp_pkey PRIMARY KEY (tenant, id)
);

CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_wizard_project_uuid
    ON {prefix}dmp (wizard_project_uuid);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_created ON {prefix}dmp (created);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_modified ON {prefix}dmp (modified);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_title ON {prefix}dmp (title);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_language ON {prefix}dmp (language);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_wizard_updated_at
    ON {prefix}dmp (wizard_updated_at);

-- Array filter columns
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_dataset_ids
    ON {prefix}dmp USING gin (dataset_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_contributor_ids
    ON {prefix}dmp USING gin (contributor_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_contact_ids
    ON {prefix}dmp USING gin (contact_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_dmp_ids
    ON {prefix}dmp USING gin (dmp_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_dmp_alternate_identifiers
    ON {prefix}dmp USING gin (dmp_alternate_identifiers);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_host_ids
    ON {prefix}dmp USING gin (host_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_funder_ids
    ON {prefix}dmp USING gin (funder_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_grant_ids
    ON {prefix}dmp USING gin (grant_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_metadata_standard_ids
    ON {prefix}dmp USING gin (metadata_standard_ids);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_license_refs
    ON {prefix}dmp USING gin (license_refs);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_distribution_formats
    ON {prefix}dmp USING gin (distribution_formats);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_distribution_data_access
    ON {prefix}dmp USING gin (distribution_data_access);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_funding_status
    ON {prefix}dmp USING gin (funding_status);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_dataset_personal_data
    ON {prefix}dmp USING gin (dataset_personal_data);
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_dataset_sensitive_data
    ON {prefix}dmp USING gin (dataset_sensitive_data);

-- Full-text search
CREATE INDEX IF NOT EXISTS ix_{prefix}dmp_search
    ON {prefix}dmp USING gin (to_tsvector('simple', search_text));
