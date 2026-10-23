"""Additive v1 schema; no legacy data is imported or modified."""
from alembic import op
revision = '0001_v1'
down_revision = None


def upgrade():
    op.execute('''
    CREATE TABLE pf_keys (
      id uuid PRIMARY KEY, tenant text NOT NULL, service text NOT NULL,
      digest text UNIQUE NOT NULL, scopes jsonb NOT NULL,
      expires_at timestamptz, revoked boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE pf_records (
      id uuid PRIMARY KEY, tenant text NOT NULL, owner_id text NOT NULL,
      kind text NOT NULL, version integer NOT NULL DEFAULT 1,
      data jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      expires_at timestamptz
    );
    CREATE INDEX pf_records_owner ON pf_records(tenant, owner_id, kind, id);
    CREATE INDEX pf_records_expiry ON pf_records(expires_at) WHERE expires_at IS NOT NULL;
    ALTER TABLE pf_records ENABLE ROW LEVEL SECURITY;
    ALTER TABLE pf_records FORCE ROW LEVEL SECURITY;
    CREATE POLICY pf_owner ON pf_records USING (
      tenant = current_setting('pf.tenant', true) AND owner_id = current_setting('pf.user', true)
    ) WITH CHECK (
      tenant = current_setting('pf.tenant', true) AND owner_id = current_setting('pf.user', true)
    );
    CREATE TABLE pf_outbox (
      job_id uuid PRIMARY KEY, tenant text NOT NULL, owner_id text NOT NULL,
      queue text NOT NULL, published_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE pf_counters (id text PRIMARY KEY, count integer NOT NULL, expires_at timestamptz NOT NULL);
    CREATE TABLE pf_audit (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, actor text NOT NULL,
      action text NOT NULL, resource uuid, outcome text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    GRANT SELECT ON pf_keys, alembic_version TO pf_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON pf_records, pf_outbox, pf_counters TO pf_app;
    GRANT INSERT ON pf_audit TO pf_app;
    GRANT USAGE ON SEQUENCE pf_audit_id_seq TO pf_app;
    ''')
    # A dedicated maintenance function exposes only tenant contexts, never document content.
    op.execute('''CREATE FUNCTION pf_expired_owners() RETURNS TABLE(tenant text, owner_id text)
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        SELECT DISTINCT r.tenant,r.owner_id FROM public.pf_records r WHERE r.expires_at <= now()
      $$;
      REVOKE ALL ON FUNCTION pf_expired_owners() FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION pf_expired_owners() TO pf_app;
    ''')


def downgrade():
    raise RuntimeError('Destructive downgrade disabled: roll back the application and retain v1 volumes.')
