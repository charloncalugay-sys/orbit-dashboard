import re, os
SYS = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(SYS, 'Refresh_ORBIT.ps1')
src = open(PS1, encoding='utf-8').read()
marks = re.findall(r'Mark-Time "([^"]+)"', src)
print('Mark-Time calls found:', len(marks))
for i, m in enumerate(marks):
    print(' ', str(i+1).rjust(2), m)
print()
print('Show-Profile call:', 'Show-Profile' in src)
print('Total lines:', len(src.split('\n')))

# Check all expected marks are present
expected = [
    'Excel kill + wait',
    'Workbook open',
    'RefreshAll complete',
    'Data model settle',
    'PT_PROD build',
    'PT_QA build',
    'PT_ASSOC build',
    'PT_PROD paste',
    'PT_QA paste',
    'PT_ASSOC paste',
    'Workbook save (post-paste)',
    'PLAIN_DATA range read',
    'prod_raw Section-To-CSV',
    'qa_raw Section-To-CSV',
    'assoc_raw Section-To-CSV',
    'CSV WriteAllText',
    'Excel close + GC',
    'Leadership export (orbit-auth.js)',
    'Parse prod_raw.csv',
    'Parse qa_raw.csv',
    'Parse assoc_raw.csv',
    'orbit-data.js write (raw)',
    'enrich_data.py (roster join)',
    'git commit',
    'git push',
    'TOTAL (before browser open)',
]
print('\n=== Coverage check ===')
marks_set = set(marks)
for e in expected:
    status = 'OK' if e in marks_set else 'MISSING'
    print(' ', status.ljust(7), e)
