import re, os

SYS = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.dirname(SYS)
PS1 = os.path.join(SYS, 'Refresh_ORBIT.ps1')

src = open(PS1, encoding='utf-8').read()

# Check where orbit-data.js is written
for m in re.finditer(r'WriteAllText', src):
    ctx = src[m.start():m.start()+150]
    print('WriteAllText at', m.start(), ':', repr(ctx[:120]))
    print()

# Check the prod parse log line
print('--- prod parse log ---')
m = re.search(r'Log \("  PROD: ".{0,200}', src)
if m:
    print(repr(src[m.start()-50:m.end()+200]))

# Check enrich block
print('--- enrich block ---')
idx = src.find('enrich_data.py')
if idx >= 0:
    print(repr(src[max(0,idx-100):idx+500]))
