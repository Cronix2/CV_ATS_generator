"""Operator-only key management. Use the migration connection, never a public endpoint."""
import argparse
import hashlib
import json
import os
import secrets
from uuid import uuid4
from sqlalchemy import create_engine, text
from app.v1.auth import SCOPES


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create-key')
    create.add_argument('--tenant', required=True)
    create.add_argument('--service', required=True)
    create.add_argument('--scopes', required=True, help='Comma-separated scopes, or all')
    create.add_argument('--days', type=int, default=90)
    revoke = commands.add_parser('revoke-key')
    revoke.add_argument('id')
    commands.add_parser('list-keys')
    args = parser.parse_args()
    engine = create_engine(os.environ['V1_MIGRATION_DATABASE_URL'], hide_parameters=True)
    with engine.begin() as conn:
        if args.command == 'create-key':
            scopes = SCOPES if args.scopes == 'all' else set(args.scopes.split(','))
            if not scopes <= SCOPES or not scopes or args.days < 1:
                parser.error('Unknown scope or invalid lifetime')
            key, ident = 'pf_v1_' + secrets.token_urlsafe(32), str(uuid4())
            conn.execute(text('''INSERT INTO pf_keys(id,tenant,service,digest,scopes,expires_at)
              VALUES(:id,:tenant,:service,:digest,CAST(:scopes AS jsonb),now()+(:days*interval '1 day'))'''),
              dict(id=ident,tenant=args.tenant,service=args.service,digest=hashlib.sha256(key.encode()).hexdigest(),
                   scopes=json.dumps(sorted(scopes)),days=args.days))
            print(json.dumps(dict(id=ident,key=key)))  # deliberate one-time operator output
        elif args.command == 'revoke-key':
            conn.execute(text('UPDATE pf_keys SET revoked=true WHERE id=:id'), dict(id=args.id))
        else:
            for row in conn.execute(text('SELECT id,tenant,service,scopes,expires_at,revoked FROM pf_keys')):
                print(json.dumps(dict(row._mapping),default=str))


if __name__ == '__main__':
    main()
