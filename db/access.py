"""Provision and verify a dedicated /ask login; passwords stay in hidden prompts.

python -m db.access --apply
No role is created by import or by a dry run.
"""
import argparse
import getpass
import os
import sys

ALLOWED=('sites','weather_readings','weather_forecasts','hazard_scores','alerts','environmental_events')
ROLE='planit_ask'
MARKER='PlanIT managed restricted ask login v1'


def provision(connection,password):
    from psycopg import sql
    if len(password)<20:raise ValueError('Use a unique password of at least 20 characters')
    role=sql.Identifier(ROLE)
    with connection.transaction():
        existing=connection.execute("SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s",(ROLE,)).fetchone()
        if existing and existing[0]!=MARKER:raise ValueError('Existing role is not managed by this tool')
        if not existing:
            connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(role))
        connection.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(role,sql.Literal(password)))
        connection.execute(sql.SQL('COMMENT ON ROLE {} IS {}').format(role,sql.Literal(MARKER)))
        memberships=connection.execute('SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON m.member=r.oid WHERE r.rolname=%s',(ROLE,)).fetchall()
        if memberships:raise ValueError('Restricted login must not inherit other roles')
        connection.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}').format(role))
        connection.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {}').format(role))
        connection.execute(sql.SQL('REVOKE ALL ON SCHEMA public FROM {}').format(role))
        connection.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
        database=connection.execute('SELECT current_database()').fetchone()[0]
        connection.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(database),role))
        for table in ALLOWED:
            connection.execute(sql.SQL('GRANT SELECT ON public.{} TO {}').format(sql.Identifier(table),role))
        for key,value in (('default_transaction_read_only','on'),('statement_timeout','5s'),('lock_timeout','1s'),('idle_in_transaction_session_timeout','5s'),('search_path','pg_catalog,public')):
            connection.execute(sql.SQL('ALTER ROLE {} SET {} = {}').format(role,sql.Identifier(key),sql.Literal(value)))
        verify(connection)


def verify(connection):
    flags=connection.execute('SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=%s',(ROLE,)).fetchone()
    if not flags or any(flags):raise ValueError('Restricted role has privileged flags')
    if connection.execute("SELECT has_schema_privilege(%s,'public','CREATE')",(ROLE,)).fetchone()[0]:
        raise ValueError('Role inherits schema CREATE (including PUBLIC); owner must reconcile schema permissions')
    for table in ALLOWED:
        if not connection.execute('SELECT has_table_privilege(%s,%s,\'SELECT\')',(ROLE,'public.'+table)).fetchone()[0]:
            raise ValueError('Required SELECT missing')
    exposed=connection.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','f') AND
      (has_table_privilege(%s,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR
       (NOT c.relname=ANY(%s) AND has_table_privilege(%s,c.oid,'SELECT')))""",(ROLE,list(ALLOWED),ROLE)).fetchall()
    if exposed:raise ValueError('Unapproved table privileges inherited; owner must reconcile them')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:
        print('Dry run. Creates managed planit_ask with SELECT only on: '+', '.join(ALLOWED)+'. Use --apply to execute with hidden password prompts.');return
    if not sys.stdin.isatty():parser.exit(2,'Use an interactive terminal for hidden password entry.\n')
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    try:
        settings=conninfo_to_dict(os.environ['DATABASE_URL']);settings['connect_timeout']=15
        settings['password']=getpass.getpass('Database owner password (hidden): ')
        password=getpass.getpass('New planit_ask password (20+ characters, hidden): ')
        if password!=getpass.getpass('Confirm new planit_ask password (hidden): '):raise ValueError('Password confirmation mismatch')
        with psycopg.connect(**settings,autocommit=True) as conn:provision(conn,password)
        check=dict(settings,user=ROLE,password=password)
        with psycopg.connect(**check,autocommit=True) as conn:
            assert conn.execute('SHOW default_transaction_read_only').fetchone()[0]=='on'
            for table in ALLOWED:conn.execute('SELECT 1 FROM public.'+table+' LIMIT 0')
        print('Restricted login created and independently connected. Store its password privately; configure it separately from the API write login.')
    except Exception:
        parser.exit(1,'Restricted-login setup/verification failed. No credentials are printed; inspect permissions with the database owner.\n')


if __name__=='__main__':main()
