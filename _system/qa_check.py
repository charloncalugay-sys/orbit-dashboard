import json, re, collections, os
F = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'orbit-data.js')
src = open(F, encoding='utf-8').read()
qa = json.loads(re.search(r'const D_QA=(\[.*?\]);', src, re.S).group(1))
fn = json.loads(re.search(r'const D_FN=(\{.*?\});', src, re.S).group(1))
by_id, by_name = fn['byId'], fn['byName']
last = {}
for n,f in by_name.items(): last.setdefault(n.split(',')[0].strip().lower(), []).append((n,f))
def fno(r):
    if r.get('id') and r['id'] in by_id: return by_id[r['id']]
    nm=(r.get('a') or '').strip()
    if nm in by_name: return by_name[nm]
    c=last.get(nm.split(',')[0].strip().lower())
    if c and len(c)==1:
        t=(nm.split(',')[1].strip().split() or [''])[0] if ',' in nm else ''
        ct=(c[0][0].split(',')[1].strip().split() or [''])[0] if ',' in c[0][0] else ''
        if t and t==ct: return c[0][1]
    return 'un'
rows=collections.Counter(); audits=collections.Counter(); assoc=collections.defaultdict(set)
for r in qa:
    k=fno(r); rows[k]+=1; audits[k]+=r.get('cnt') or 0; assoc[k].add(r.get('id') or r.get('a'))
LABEL={'cash-control':'Cash Control','cob':'COB','collections':'Collections','dispute-triage':'DISPUTE TRIAGE','disputes-intakes':'Disputes & Intakes','iqt':'IQT','non-cob':'NON COB','prepay':'Prepay','un':'(unclassified)'}
hdr = '{:<20}{:>10}{:>10}{:>8}'.format('Function','D_QA Rows','Audits','Assoc')
print(hdr); print('-'*len(hdr))
tr=ta=0
for k in ['cash-control','cob','collections','dispute-triage','disputes-intakes','iqt','non-cob','prepay','un']:
    print('{:<20}{:>10}{:>10}{:>8}'.format(LABEL[k], rows.get(k,0), audits.get(k,0), len(assoc.get(k,set()))))
    tr+=rows.get(k,0); ta+=audits.get(k,0)
print('-'*len(hdr)); print('{:<20}{:>10}{:>10}'.format('TOTAL', tr, ta))
meta = json.loads(re.search(r'const D_FN_META=(\[.*?\]);', src, re.S).group(1))
print()
print('D_FN_META:', ', '.join('{}={}'.format(m['key'], m['state']) for m in meta))
