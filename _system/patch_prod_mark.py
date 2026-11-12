import os

SYS = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(SYS, 'Refresh_ORBIT.ps1')
src = open(PS1, encoding='utf-8').read()

OLD = 'Log ("  PROD: " + $prodRows.Count + " rows, " + $orgMgrs.Count + " managers") Gray\n\n# Parse QA'
NEW = 'Log ("  PROD: " + $prodRows.Count + " rows, " + $orgMgrs.Count + " managers") Gray\nMark-Time "Parse prod_raw.csv"\n\n# Parse QA'

if OLD in src:
    src = src.replace(OLD, NEW, 1)
    open(PS1, 'w', encoding='utf-8').write(src)
    print('Parse prod_raw.csv mark patched.')
else:
    print('OLD not found. Searching...')
    idx = src.find('PROD: ')
    while idx >= 0:
        print(repr(src[idx:idx+150]))
        idx = src.find('PROD: ', idx+1)
