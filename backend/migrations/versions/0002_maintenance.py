"""Bound secret retention and privileged expiry-only maintenance."""

from alembic import op

revision = "0002_maintenance"
down_revision = "0001_v1"


def upgrade():
    op.execute("""
      DROP FUNCTION pf_expired_owners();
      CREATE FUNCTION pf_purge_expired() RETURNS void
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
      BEGIN
        UPDATE public.pf_records SET data=data || jsonb_build_object('secret',NULL)
          WHERE kind='job' AND data->>'secret' IS NOT NULL
          AND (data->>'secret_expires')::double precision < extract(epoch FROM now());
        DELETE FROM public.pf_records WHERE expires_at<=now();
        DELETE FROM public.pf_outbox o WHERE NOT EXISTS (SELECT 1 FROM public.pf_records r WHERE r.id=o.job_id);
        DELETE FROM public.pf_counters WHERE expires_at<=now();
        DELETE FROM public.pf_audit WHERE created_at<now()-interval '90 days';
      END $$;
      REVOKE ALL ON FUNCTION pf_purge_expired() FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION pf_purge_expired() TO pf_app;
    """)


def downgrade():
    raise RuntimeError("Rollback application images; retain the database.")
