#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix the base stacking order of the commute circles in offline/index.html.

They were added 10->40, so 40 ended up drawn on top (and 30 over 20). Adding
them 40->10 instead makes 10 the topmost and 40 the bottom, matching the
desired order. The layer-zorder script still re-enforces this after toggles.

Idempotent: the target order is the same no matter how many times this runs.
"""
from pathlib import Path

root = Path(__file__).resolve().parent
index = root / 'offline' / 'index.html'
if not index.exists():
    raise SystemExit('Missing offline/index.html')

text = index.read_text(encoding='utf-8')
backup = root / 'offline' / 'index_before_commute_add_order.html'
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

old = '[10,15,20,30,40].forEach(m => commute[m].addTo(map));'
new = '[40,30,20,15,10].forEach(m => commute[m].addTo(map));'

n = text.count(old)
if n:
    text = text.replace(old, new)
    index.write_text(text, encoding='utf-8')
    print('Done: commute base add-order set to 40->10 (10 on top). Replaced %d occurrence(s).' % n)
elif new in text:
    print('Already applied: commute base add-order is 40->10. No change.')
else:
    raise SystemExit('Could not find the commute add-order line; index.html structure changed.')
