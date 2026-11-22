"""Translation completeness audit for retained frontend keys.

Usage: python backend/scripts/translation_audit.py
Checks that keys used via t('...') exist in all locale files.
"""
import json, re, glob, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCALES = os.path.join(ROOT, 'frontend', 'src', 'locales')
LANGS = ['en', 'kn', 'hi', 'ta', 'te']

def load():
    data = {}
    for l in LANGS:
        p = os.path.join(LOCALES, f'{l}.json')
        with open(p, encoding='utf-8') as f:
            data[l] = json.load(f)
    return data

def used_keys():
    used = set()
    for pat in ['frontend/src/**/*.js', 'frontend/src/**/*.jsx']:
        for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
            with open(p, encoding='utf-8', errors='ignore') as f:
                t = f.read()
            for m in re.finditer(r"\bt\(\s*['\"]([^'\"]+)['\"]", t):
                used.add(m.group(1))
    return used

def hardcoded_candidates():
    candidates=[]
    for pat in ['frontend/src/pages/**/*.jsx','frontend/src/components/**/*.jsx']:
        for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
            rel=os.path.relpath(p, ROOT).replace('\\','/')
            with open(p,encoding='utf-8',errors='ignore') as f:
                for i,line in enumerate(f,1):
                    if re.search(r"^\s*(//|\*|/\*)", line): continue
                    for m in re.finditer(r">\s*([^<>{}\n][^<>{}]*)\s*<", line):
                        txt=m.group(1).strip()
                        if len(txt)<2 or not re.search(r"[A-Za-z]{3}",txt): continue
                        if any(x in txt for x in ['className','{','}','$']): continue
                        candidates.append((rel,i,txt[:80]))
                    for m in re.finditer(r'(?:placeholder|title|aria-label)=["\']([^"\'{}]*[A-Za-z]{3}[^"\'{}]*)["\']', line):
                        txt=m.group(1).strip()
                        candidates.append((rel,i,'ATTR:'+txt[:80]))
    return candidates

def main():
    data = load()
    used = used_keys()
    ok = True
    print(f'USED_KEYS {len(used)}')
    for l in LANGS:
        missing = sorted([k for k in used if k not in data[l]])
        empty = sorted([k for k,v in data[l].items() if k in used and (v is None or str(v).strip()=='')])
        print(f'{l}: missing={len(missing)} empty={len(empty)} total={len(data[l])}')
        for k in missing[:20]:
            print(f'  MISSING {k}')
            ok = False
        for k in empty[:20]:
            print(f'  EMPTY {k}')
            ok = False
    en = set(data['en'].keys())
    for l in LANGS:
        if l == 'en': continue
        miss = sorted(en - set(data[l].keys()))
        extra = sorted(set(data[l].keys()) - en)
        if miss or extra:
            print(f'{l} parity missing={len(miss)} extra={len(extra)}')
            ok = False
    hc=hardcoded_candidates()
    print(f'HARDCODED_CANDIDATES {len(hc)}')
    for rel,i,txt in hc[:60]:
        print(f'  {rel}:{i}: {txt}')
    if hc:
        ok = False
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(main())
