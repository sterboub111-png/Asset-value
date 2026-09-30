import re, glob, json
S = '"([^"]*)"'
keys = set()
pats = [r'\bt\(' + S, r'label: ' + S, r'title: ' + S, r'hint: ' + S, r'empty: ' + S, r'crumb: ' + S,
        r'section: ' + S, r'desc: ' + S, r'reason\]? ?= ?' + S]
for f in glob.glob('web/src/**/*.ts', recursive=True):
    if f.endswith('ar.ts'): continue
    s = open(f, encoding='utf-8').read()
    for p in pats:
        keys.update(re.findall(p, s))
    # statuses / list literals
    for m in re.findall(r'\[((?:"[^"]+",? ?)+)\]', s):
        keys.update(re.findall(S, m))
for f in ['app/reports.py', 'app/services.py']:
    s = open(f, encoding='utf-8').read()
    keys.update(re.findall(r'\("\w+", ' + S + r', "\w+"\)', s))
    keys.update(re.findall(r'group="([^"]+)"', s))
    keys.update(re.findall(r'ApiError\(f?' + S, s))
    keys.update(re.findall(r'reason(?:\"\])? ?= ?' + S, s))
    keys.update(re.findall(r'line\[\"reason\"\] = ' + S, s))
keys = {k for k in keys if k and not k.startswith('/') and not k.startswith('#') and '{d[' not in k and '{field}' not in k and '{req}' not in k and '{code}' not in k}
open('data/_keys.json', 'w', encoding='utf-8').write(json.dumps(sorted(keys), ensure_ascii=False, indent=0))
print(len(keys))
