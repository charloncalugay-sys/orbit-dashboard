import json, re

src = open(
    r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH\orbit-data.js',
    encoding='utf-8'
).read()

def arr(name):
    m = re.search(r'const %s=(\[.*?\]);' % name, src, re.S)
    return json.loads(m.group(1)) if m else []

prod = arr('D_PROD')
qa   = arr('D_QA')
dim  = arr('D_DIM')

dim_by_id   = {d['id']: d for d in dim}
dim_by_name = {d['n']: d['id'] for d in dim if d.get('n')}

DUPES = [
    ('Buan, Angelica',           'AL39630', 'AL56839'),
    ('Docot, Jonea Joy',         None,      'AH89297'),
    ('Embate, Derrick',          None,      'AL56613'),
    ('Fabian, Rovie-Ann',        None,      'AL42174'),
    ('Godoy, Christine Angela',  None,      'AL18961'),
    ('Hernandez, Laine Britney', None,      'AM21381'),
    ('Merabite, Coney Liza',     None,      'AL70805'),
]

print('=== Remaining 7 duplicate analysis ===')
for name, prod_key, qa_key in DUPES:
    prod_rows   = [r for r in prod if r.get('a') == name]
    dim_for_name = dim_by_name.get(name)
    dim_for_qa   = dim_by_id.get(qa_key, {})
    qa_rows      = [r for r in qa  if r.get('id') == qa_key]
    qa_names     = sorted(set(r.get('a', '') for r in qa_rows))[:3]

    print()
    print('  %s' % name)
    print('    D_PROD rows: %d | dim_by_name lookup: %s' % (len(prod_rows), repr(dim_for_name)))
    print('    D_QA id=%s | names=%s | fn=%s' % (
        qa_key, qa_names, set(r.get('fn','') for r in qa_rows)))
    print('    D_DIM[%s]: n=%r am=%r' % (
        qa_key, dim_for_qa.get('n', 'NOT IN DIM'), dim_for_qa.get('am', '?')))
    # What is the D_DIM entry for the prod name?
    if dim_for_name:
        d2 = dim_by_id[dim_for_name]
        print('    D_DIM[%s] (prod name): n=%r' % (dim_for_name, d2.get('n')))

print()
print('=== Root cause ===')
print('These 7 cases arise because:')
print('  - D_PROD name has NO D_DIM entry -> keyed as n:name (fallback)')
print('  - D_QA id has a D_DIM entry with a DIFFERENT name -> keyed by OPR ID')
print('  => Two map keys for the same person.')
print()
print('Fix: also check if the D_QA OPR ID DIM name matches the D_PROD name.')
print('If D_DIM[qa_id].n == prod_name -> they are the same person; merge.')
print()

# How many D_PROD names have no D_DIM entry?
prod_names = set(r.get('a','') for r in prod if r.get('a'))
no_dim = [n for n in prod_names if n not in dim_by_name]
print('D_PROD names with no D_DIM entry: %d' % len(no_dim))
for n in sorted(no_dim):
    print('  %r' % n)
