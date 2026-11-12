import csv, os, re, sys

SYS = os.path.dirname(os.path.abspath(__file__))
qa_path = os.path.join(SYS, 'qa_raw.csv')
lines = open(qa_path, encoding='utf-8-sig').readlines()

names, oprs, nums, fns, blanks = [], [], [], [], []
for l in lines[1:]:
    v = l.split(',')[0].strip().strip('"')
    if not v:
        blanks.append(v)
    elif re.match(r'^[A-Z]{2}\d+$', v):
        oprs.append(v)
    elif re.match(r'^\d+$', v):
        nums.append(v)
    elif ',' in v:
        names.append(v)
    else:
        fns.append(v)

print('Names (Last, First):', len(names), names[:3])
print('OPR IDs:', len(oprs), oprs[:5])
print('Numeric IDs:', len(nums), nums[:5])
print('Other strings:', len(fns), fns[:10])
print('Blanks:', len(blanks))

print('\n--- first 60 lines of qa_raw.csv ---')
for i, l in enumerate(lines[1:61]):
    print(str(i+1).rjust(3), l.rstrip())
