"""Allowlisted read-only query executor for Alan's /ask integration.

Requires planit_ask credentials. Returns bounded rows, never credentials.
"""
import json
from db.access import ALLOWED,ROLE

NODES={'RawStmt','SelectStmt','ResTarget','ColumnRef','String','Integer','Float','Boolean',
       'A_Const','RangeVar','A_Expr','BoolExpr','NullTest','TypeCast','TypeName','SortBy',
       'FuncCall','JoinExpr','Alias','A_Star','CaseExpr','CaseWhen','CoalesceExpr','MinMaxExpr',
       'List','SQLValueFunction','SubLink','RangeSubselect'}
FUNCTIONS={'count','sum','avg','min','max','abs','round','date_trunc','extract','date_part','now','greatest','least'}
TYPES={'int2','int4','int8','float4','float8','numeric','text','bool','date','timestamp','timestamptz','interval','varchar'}
OPERATORS={'=','<>','!=','<','>','<=','>=','+','-','*','/','%','~~','!~~','~~*','!~~*'}


def strings(values):
    return [v['String']['sval'].lower() for v in values if isinstance(v,dict) and 'String' in v]


def validate_query(query):
    from pglast.parser import parse_sql_json
    if not isinstance(query,str) or len(query)>12000:raise ValueError('Invalid query size')
    try:tree=json.loads(parse_sql_json(query))
    except Exception:raise ValueError('Invalid SQL syntax') from None
    statements=tree.get('stmts',[])
    if len(statements)!=1 or set(statements[0]['stmt'])!={'SelectStmt'}:raise ValueError('One SELECT is required')
    referenced=set()
    def walk(value,depth=0):
        if depth>30:raise ValueError('Query nesting is too deep')
        if isinstance(value,list):
            for item in value:walk(item,depth+1)
        elif isinstance(value,dict):
            for key,item in value.items():
                if key and key[0].isupper() and key not in NODES:raise ValueError('Unsupported SQL construct: '+key)
                if key=='SelectStmt' and any(item.get(k) for k in ('intoClause','lockingClause','withClause')):
                    raise ValueError('SELECT INTO, locking and WITH are not supported')
                if key=='RangeVar':
                    if item.get('catalogname') or item.get('schemaname','public')!='public' or item.get('relname') not in ALLOWED:
                        raise ValueError('Relation is not allowlisted')
                    referenced.add(item['relname'])
                if key=='FuncCall':
                    name=strings(item.get('funcname',[]))
                    if not name or name[-1] not in FUNCTIONS or len(name)>2 or len(name)==2 and name[0]!='pg_catalog':
                        raise ValueError('Function is not allowlisted')
                if key=='TypeName':
                    name=strings(item.get('names',[]))
                    if not name or name[-1] not in TYPES or len(name)>2 or len(name)==2 and name[0]!='pg_catalog':
                        raise ValueError('Type is not allowlisted')
                if key=='A_Expr':
                    name=strings(item.get('name',[]))
                    if len(name)!=1 or name[0] not in OPERATORS:raise ValueError('Operator is not allowlisted')
                walk(item,depth+1)
    walk(tree)
    if not referenced:raise ValueError('Query must read an approved data table')
    return query.strip().rstrip(';')


def execute(connection,query):
    query=validate_query(query)
    with connection.transaction():
        connection.execute('SET TRANSACTION READ ONLY')
        connection.execute("SET LOCAL statement_timeout='5s'")
        connection.execute("SET LOCAL search_path=pg_catalog,public")
        if connection.execute('SELECT current_user').fetchone()[0]!=ROLE:raise ValueError('Use the dedicated restricted /ask login')
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM (\n'+query+'\n) AS planit_answer LIMIT 101')
            columns=[c.name for c in cursor.description];rows=cursor.fetchall()
    return {'columns':columns,'rows':[dict(zip(columns,row)) for row in rows[:100]],'truncated':len(rows)>100}


def connect():
    """Separate secret configuration; never fall back to the app write login."""
    import os
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    if not os.getenv('PLANIT_ASK_DATABASE_URL') or not os.getenv('PLANIT_ASK_PASSWORD'):
        raise ValueError('Configure the dedicated /ask connection privately')
    settings=conninfo_to_dict(os.environ['PLANIT_ASK_DATABASE_URL'])
    if settings.get('user')!=ROLE:raise ValueError('The /ask URI must use planit_ask')
    settings.update(password=os.environ['PLANIT_ASK_PASSWORD'],connect_timeout=15)
    settings.setdefault('sslmode','require')
    return psycopg.connect(**settings,autocommit=True)
