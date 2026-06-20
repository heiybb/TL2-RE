import json, sys, collections
path = sys.argv[1] if len(sys.argv) > 1 else "tools/eval_all_mpp_results2.jsonl"
rows = [json.loads(l) for l in open(path) if l.strip()]
st = collections.Counter(r["status"] for r in rows)
print(f"=== {len(rows)} layouts ===")
for k, v in st.most_common():
    print(f"  {k:14s}: {v}  ({100*v/len(rows):.1f}%)")

ok = [r for r in rows if r["status"] == "ok"]
tot_cells = sum(r["cells"] for r in ok)
S = lambda k: sum(r.get(k, 0) for r in ok)
tot_diff = S("diff")
# pathing-relevant = walk<->wall + walk<->void; cosmetic = wall<->void
path_err = S("w2W") + S("W2w") + S("w2V") + S("V2w")
cosmetic = S("W2V") + S("V2W")
print(f"\n--- cell accuracy over {len(ok)} dims-matching layouts ({tot_cells:,} cells) ---")
print(f"  raw differing cells     : {tot_diff:,}  -> raw match {100*(1-tot_diff/tot_cells):.4f}%")
print(f"  PATHING-relevant diffs  : {path_err:,}  -> pathing match {100*(1-path_err/tot_cells):.4f}%")
print(f"     walk->wall (over)    : {S('w2W'):,}  ({100*S('w2W')/tot_cells:.4f}%)")
print(f"     wall->walk (under)   : {S('W2w'):,}  ({100*S('W2w')/tot_cells:.4f}%)")
print(f"     walk->void (footprint): {S('w2V'):,}  ({100*S('w2V')/tot_cells:.4f}%)")
print(f"     void->walk (footprint): {S('V2w'):,}  ({100*S('V2w')/tot_cells:.4f}%)")
print(f"  COSMETIC (wall<->void)  : {cosmetic:,}  ({100*cosmetic/tot_cells:.4f}%)  [both impassable]")

import math
pml = sorted(100*(1 - r["diff"]/r["cells"]) for r in ok if r["cells"])
ppath = sorted(100*(1 - (r.get('w2W',0)+r.get('W2w',0)+r.get('w2V',0)+r.get('V2w',0))/r["cells"]) for r in ok if r["cells"])
def pct(a, p): return a[min(len(a)-1, int(len(a)*p))]
print(f"\n--- per-layout RAW match% ---  min={pml[0]:.2f} p10={pct(pml,.1):.2f} median={pct(pml,.5):.3f} p90={pct(pml,.9):.4f} max={pml[-1]:.4f}")
print(f"--- per-layout PATHING match% ---  min={ppath[0]:.2f} p10={pct(ppath,.1):.2f} median={pct(ppath,.5):.3f} p90={pct(ppath,.9):.4f}")
print(f"  grid byte-exact (diff==0): {sum(1 for r in ok if r['diff']==0)} ({100*sum(1 for r in ok if r['diff']==0)/len(ok):.1f}% of dims-match)")
print(f"  pathing-exact (0 path diffs): {sum(1 for p in ppath if p>=100.0)} ({100*sum(1 for p in ppath if p>=100.0)/len(ppath):.1f}%)")
print(f"  raw >=99%: {sum(1 for p in pml if p>=99)} ({100*sum(1 for p in pml if p>=99)/len(pml):.1f}%)   pathing >=99%: {sum(1 for p in ppath if p>=99)} ({100*sum(1 for p in ppath if p>=99)/len(ppath):.1f}%)")

# group worst by top-dir to see which tile families dominate the gap
fam = collections.defaultdict(lambda: [0, 0])
for r in ok:
    key = r["rel"].split("\\")[0]
    fam[key][0] += r.get("w2W",0)+r.get("W2w",0)+r.get("w2V",0)+r.get("V2w",0)
    fam[key][1] += r["cells"]
print("\n--- pathing-error share by act/zone (top 12 by error cells) ---")
for k, (err, cells) in sorted(fam.items(), key=lambda x: -x[1][0])[:12]:
    print(f"  {k:24s} pathing-err={err:>8,}  ({100*err/cells:.3f}% of {cells:,})")

print("\n--- 12 worst layouts by PATHING diff% ---")
def pd(r): return (r.get('w2W',0)+r.get('W2w',0)+r.get('w2V',0)+r.get('V2w',0))/r["cells"]
for r in sorted(ok, key=lambda r:-pd(r))[:12]:
    print(f"  path {100*(1-pd(r)):6.2f}%  o{r.get('w2W',0)} u{r.get('W2w',0)} wV{r.get('w2V',0)} Vw{r.get('V2w',0)}  cells={r['cells']:>7}  {r['rel']}")
