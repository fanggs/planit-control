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
MAX_SELECT_DEPTH=5
MAX_EXPRESSION_DEPTH=32
MAX_AST_NODES=1500
MAX_JSON_DEPTH=160
EXPRESSION_NODES={'A_Expr','BoolExpr','CaseExpr','CaseWhen','FuncCall','CoalesceExpr','MinMaxExpr','NullTest','TypeCast'}


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
    # SQL nesting and expression complexity are independent of JSON wrappers.
    # An iterative walk also bounds traversal without Python recursion growth.
    stack=[(tree,0,0,0)];nodes=0;containers=0
    while stack:
        value,depth,select_depth,expression_depth=stack.pop()
        if depth>MAX_JSON_DEPTH:raise ValueError('SQL representation is too deep')
        if isinstance(value,(list,dict)):
            containers+=1
            if containers>15000:raise ValueError('SQL representation is too large')
        if isinstance(value,list):
            stack.extend((item,depth+1,select_depth,expression_depth) for item in value)
        elif isinstance(value,dict):
            for key,item in value.items():
                if key and key[0].isupper() and key not in NODES:raise ValueError('Unsupported SQL construct: '+key)
                if key in NODES:
                    nodes+=1
                    if nodes>MAX_AST_NODES:raise ValueError('Too many SQL nodes')
                child_select_depth=select_depth+(key=='SelectStmt')
                child_expression_depth=expression_depth+(key in EXPRESSION_NODES)
                if child_select_depth>MAX_SELECT_DEPTH:raise ValueError('Too many nested SELECTs')
                if child_expression_depth>MAX_EXPRESSION_DEPTH:raise ValueError('SQL expression nesting is too deep')
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
                stack.append((item,depth+1,child_select_depth,child_expression_depth))
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
