import re
src = open(r'C:\Users\AL70683\OneDrive - Elevance Health\IGNITE PROJECTS\ORBIT\ORBIT DASH\_system\Refresh_ORBIT.ps1', encoding='utf-8').read()
for m in re.finditer(r'WriteAllText', src):
    ctx = src[m.start():m.start()+200]
    print(m.start(), repr(ctx[:120]))
