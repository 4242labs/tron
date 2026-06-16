#!/usr/bin/env sh
set -e

# Drop the view that blocks prisma db push on every cold start.
# LiteLLM creates LiteLLM_VerificationTokenView in older schema versions;
# v1.63.14 tries to drop the underlying column without CASCADE and fails.
python3 -c "
import os, urllib.parse
url = os.environ.get('DATABASE_URL', '')
if url:
    try:
        import psycopg2
        conn = psycopg2.connect(url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('DROP VIEW IF EXISTS \"LiteLLM_VerificationTokenView\" CASCADE')
        conn.close()
        print('entrypoint: view drop ok')
    except Exception as e:
        print('entrypoint: view drop skipped:', e)
" || true

exec litellm "$@"
