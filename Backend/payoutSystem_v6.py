# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v6.py
# ──────────────────────────
# • Skips any ledger row with Done? == "Yes"
# • Same 3-payment soft cap, BANK overflow, cycle cancellation
# • Adds verbose progress prints so you can see what happened.
# """

# from __future__ import annotations
# import argparse, csv, re, sys
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple
# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# # ── tiny helpers ────────────────────────────────────────────────────────────
# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)
# def normal_forms(raw:str)->list[str]:
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     out=[raw.strip().lower()]
#     if before: out.append(before.strip().lower())
#     if inside: out.append(inside.strip().lower())
#     return list(dict.fromkeys(out))

# def parse_money(v)->Decimal:
#     if pd.isna(v): return Decimal("0")
#     return Decimal(str(v).replace("$","").replace(",","").strip())
# def money_str(x:Decimal)->str: return f"{x.quantize(CENT)}"

# # ── payment-method DB ───────────────────────────────────────────────────────
# def load_payment_db(path:Path)->Dict[str,List[str]]:
#     if not path.exists(): return {}
#     df=pd.read_csv(path); db:Dict[str,List[str]]={}
#     for _,row in df.iterrows():
#         raw=row["Player Name"]; handles=[]
#         for col,val in row.items():
#             if col=="Player Name": continue
#             val=str(val).strip()
#             if not val or val.lower()=="nan": continue
#             lbl=col.strip()
#             if lbl.lower()=="venmo" and not val.startswith("@"): val="@"+val
#             if lbl.lower()=="cashapp"and not val.startswith("$"): val="$"+val
#             handles.append(f"{lbl}: {val}")
#         for k in normal_forms(raw):
#             db.setdefault(k,[])
#             for h in handles:
#                 if h not in db[k]: db[k].append(h)
#     return db

# def method_string(name:str,amt:Decimal,db)->str:
#     if name=="BANK": return f"Internal bank transfer of ${money_str(amt)}"
#     for k in normal_forms(name):
#         if k in db: return f"Pay user ${money_str(amt)} on "+", ".join(f"({h})"for h in db[k])
#     return f"Pay user ${money_str(amt)} on (Venmo: )"

# # ── classification (skips Done? == Yes) ─────────────────────────────────────
# def classify(df:pd.DataFrame):
#     cred, debt=[],[]
#     bank=Decimal("0")
#     for idx,row in df.iterrows():
#         if str(row.get("Done?","")).strip().lower()=="yes": continue
#         disp=str(row["Player Name"]).strip()
#         node=f"{disp} @row{idx}"
#         cred_flag=str(row["Credit?"]).strip().lower()
#         received=parse_money(row.get("$ Received",0))
#         ending=parse_money(row.get("Ending Stack",0))
#         pl=parse_money(row.get("P/L Player",0))
#         send_out=parse_money(row.get("Send Out",0))
#         sent=parse_money(row.get("$ Sent",0))

#         if cred_flag!="yes":
#             bank+=received
#             if ending>0: cred.append((node,sent))
#         else:
#             if pl<0: debt.append((node,abs(send_out)))
#             elif pl>0: cred.append((node,sent))
#     return cred,debt,bank

# # ── settlement / cycle-cancel same as before ────────────────────────────────
# Transfer=Tuple[str,str,Decimal]
# def settle(cred_in,debt_in,max_out=3)->List[Transfer]:
#     cred=deque(sorted([(n,Decimal(a)) for n,a in cred_in],key=lambda x:x[1],reverse=True))
#     debt=sorted([(n,Decimal(a)) for n,a in debt_in],key=lambda x:x[1],reverse=True)
#     tx, outcnt=[],defaultdict(int)
#     for d,owe in debt:
#         while owe>0:
#             slots=max_out-outcnt[d]
#             if slots==0 or not cred or cred[0][1]==0:
#                 tx.append((d,"BANK",owe)); outcnt[d]+=1; break
#             c,need=cred[0]
#             if slots==1:
#                 if need>=owe:
#                     tx.append((d,c,owe)); outcnt[d]+=1; need-=owe
#                     if need==0: cred.popleft()
#                 else:
#                     tx.append((d,"BANK",owe)); outcnt[d]+=1
#                 break
#             pay=min(owe,need)
#             tx.append((d,c,pay)); outcnt[d]+=1
#             owe-=pay; need-=pay
#             if need==0: cred.popleft()
#             else: cred[0]=(c,need)
#     for c,need in cred:
#         if need>0: tx.append(("BANK",c,need))
#     return tx

# def cancel_cycles(ts:List[Transfer])->List[Transfer]:
#     g=defaultdict(Decimal)
#     for fr,to,amt in ts:
#         if fr!=to and amt: g[(fr,to)]+=amt
#     changed=True
#     while changed:
#         changed=False
#         for (a,b),ab in list(g.items()):
#             if a=="BANK" or b=="BANK": continue
#             for (b2,c),bc in list(g.items()):
#                 if b2!=b or c=="BANK": continue
#                 if (c,a) in g:
#                     ca=g[(c,a)]; x=min(ab,bc,ca)
#                     for e in [(a,b),(b,c),(c,a)]:
#                         g[e]-=x
#                         if g[e]==0: del g[e]
#                     changed=True; break
#             if changed: break
#     return [(fr,to,amt) for (fr,to),amt in g.items()]

# # ── driver ──────────────────────────────────────────────────────────────────
# def main()->None:
#     p=argparse.ArgumentParser()
#     p.add_argument("--csv",required=True)
#     args=p.parse_args()
#     ledger=Path(args.csv).expanduser()
#     if not ledger.exists(): sys.exit("Ledger file not found")

#     root=Path(__file__).resolve().parents[1]
#     print(f"Reading ledger: {ledger}", flush=True)

#     pay_db=load_payment_db(root/"Payment Type"/"Payment Methods.csv")
#     df=pd.read_csv(ledger)
#     credit, debt, bank=classify(df)
#     print(f"Rows kept after Done?==Yes filter: {len(credit)+len(debt)}", flush=True)

#     if bank>0: debt.append(("BANK",bank))
#     elif bank<0: credit.append(("BANK",-bank))

#     tx=cancel_cycles(settle(credit,debt,max_out=3))

#     merged=defaultdict(Decimal)
#     for fr,to,amt in tx: merged[(fr,to)]+=amt
#     tx=sorted([(fr,to,amt) for (fr,to),amt in merged.items()],
#               key=lambda x:(x[0],x[1]))

#     tag=re.search(r"(\d{1,2}_\d{1,2}_\d{2})",ledger.stem)
#     tag=tag.group(1) if tag else "output"
#     out=root/"Transactions"/f"{tag}_transactions_v6.csv"
#     out.parent.mkdir(exist_ok=True)

#     with out.open("w",newline="") as f:
#         w=csv.writer(f); w.writerow(["From","To","Amount","Method"])
#         for fr,to,amt in tx:
#             fr_disp, to_disp = fr.split(" @row")[0], to.split(" @row")[0]
#             w.writerow([fr_disp,to_disp,money_str(amt),
#                         method_string(to_disp,amt,pay_db)])

#     print(f"✅  Wrote {out}  ({len(tx)} transfers, cap ≤3)", flush=True)

# if __name__=="__main__":
#     main()







# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v6.py
# ──────────────────────────
# • Skips any ledger row with Done? == "Yes"
# • Greedy netting with soft/hard caps (--soft default 3, --hard default 4)
# • BANK overflow when soft cap is reached
# • 3-cycle cancellation
# • Verbose prints so you can follow progress
# """

# from __future__ import annotations
# import argparse, csv, re, sys
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple
# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# # ── tiny helpers ────────────────────────────────────────────────────────────
# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)
# def normal_forms(raw: str) -> List[str]:
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     out = [raw.strip().lower()]
#     if before: out.append(before.strip().lower())
#     if inside: out.append(inside.strip().lower())
#     return list(dict.fromkeys(out))

# def parse_money(v) -> Decimal:
#     if pd.isna(v):
#         return Decimal("0")
#     return Decimal(str(v).replace("$", "").replace(",", "").strip())

# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"

# # ── payment-method DB ───────────────────────────────────────────────────────
# def load_payment_db(path: Path) -> Dict[str, List[str]]:
#     if not path.exists():
#         return {}
#     df = pd.read_csv(path)
#     db: Dict[str, List[str]] = {}
#     for _, row in df.iterrows():
#         raw = row["Player Name"]
#         handles: List[str] = []
#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             lbl = col.strip().lower()
#             if lbl == "venmo"   and not val.startswith("@"):
#                 val = "@" + val
#             if lbl == "cashapp" and not val.startswith("$"):
#                 val = "$" + val
#             handles.append(f"{col.strip()}: {val}")
#         for k in normal_forms(str(raw)):
#             db.setdefault(k, [])
#             for h in handles:
#                 if h not in db[k]:
#                     db[k].append(h)
#     return db

# def method_string(name: str, amt: Decimal, db: Dict[str, List[str]]) -> str:
#     if name == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"
#     for k in normal_forms(name):
#         if k in db:
#             return (
#                 f"Pay user ${money_str(amt)} on " +
#                 ", ".join(f"({h})" for h in db[k])
#             )
#     return f"Pay user ${money_str(amt)} on (Venmo: )"

# # ── classification (skips Done? == Yes) ─────────────────────────────────────
# def classify(df: pd.DataFrame) -> Tuple[
#         List[Tuple[str, Decimal]],
#         List[Tuple[str, Decimal]],
#         Decimal]:
#     creditors: List[Tuple[str, Decimal]] = []
#     debtors:   List[Tuple[str, Decimal]] = []
#     bank = Decimal("0")

#     for idx, row in df.iterrows():
#         if str(row.get("Done?", "")).strip().lower() == "yes":
#             continue

#         disp = str(row["Player Name"]).strip()
#         node = f"{disp} @row{idx}"

#         cred_flag = str(row["Credit?"]).strip().lower()
#         received  = parse_money(row.get("$ Received", 0))
#         ending    = parse_money(row.get("Ending Stack", 0))
#         pl        = parse_money(row.get("P/L Player", 0))
#         send_out  = parse_money(row.get("Send Out", 0))
#         sent_col  = parse_money(row.get("$ Sent", 0))

#         if cred_flag != "yes":
#             bank += received
#             if ending > 0:
#                 creditors.append((node, sent_col))
#         else:
#             if pl < 0:
#                 debtors.append((node, abs(send_out)))
#             elif pl > 0:
#                 creditors.append((node, sent_col))

#     return creditors, debtors, bank

# # ── settlement with soft/hard caps ──────────────────────────────────────────
# Transfer = Tuple[str, str, Decimal]

# def settle(
#     creditors_in: List[Tuple[str, Decimal]],
#     debtors_in:   List[Tuple[str, Decimal]],
#     soft: int,
#     hard: int
# ) -> List[Transfer]:
#     creditors = deque(sorted(creditors_in, key=lambda x: x[1], reverse=True))
#     debtors   = sorted(debtors_in,    key=lambda x: x[1], reverse=True)

#     transfers: List[Transfer] = []
#     outcnt = defaultdict(int)

#     for debtor, owe in debtors:
#         while owe > 0:
#             # no more than `hard` transfers
#             if outcnt[debtor] >= hard:
#                 raise RuntimeError(f"{debtor} exceeded hard cap of {hard}")

#             # if at or past soft cap → dump remainder to BANK
#             if outcnt[debtor] >= soft:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break

#             # normal greedy payment to largest creditor
#             cred, need = creditors[0]
#             pay = min(owe, need)

#             transfers.append((debtor, cred, pay))
#             outcnt[debtor] += 1
#             owe -= pay
#             need -= pay

#             if need == 0:
#                 creditors.popleft()
#             else:
#                 creditors[0] = (cred, need)

#     # BANK pays off any remaining creditors
#     for cred, need in creditors:
#         if need > 0:
#             transfers.append(("BANK", cred, need))

#     return transfers

# # ── 3-cycle cancellation ───────────────────────────────────────────────────
# def cancel_cycles(ts: List[Transfer]) -> List[Transfer]:
#     graph = defaultdict(Decimal)
#     for fr, to, amt in ts:
#         if fr != to and amt:
#             graph[(fr, to)] += amt

#     changed = True
#     while changed:
#         changed = False
#         for (a, b), ab in list(graph.items()):
#             if a == "BANK" or b == "BANK":
#                 continue
#             for (b2, c), bc in list(graph.items()):
#                 if b2 != b or c == "BANK":
#                     continue
#                 if (c, a) in graph:
#                     ca = graph[(c, a)]
#                     x = min(ab, bc, ca)
#                     for e in [(a, b), (b, c), (c, a)]:
#                         graph[e] -= x
#                         if graph[e] == 0:
#                             del graph[e]
#                     changed = True
#                     break
#             if changed:
#                 break

#     return [(fr, to, amt) for (fr, to), amt in graph.items()]

# # ── driver ──────────────────────────────────────────────────────────────────
# def main() -> None:
#     p = argparse.ArgumentParser()
#     p.add_argument("--csv",  required=True,
#                    help="Path to ledger CSV (Ledger Data/…)") 
#     p.add_argument("--soft", type=int, default=3,
#                    help="Soft cap on outgoing transfers (default 3)")
#     p.add_argument("--hard", type=int, default=4,
#                    help="Hard cap on outgoing transfers (default 4)")
#     args = p.parse_args()

#     ledger = Path(args.csv).expanduser()
#     if not ledger.exists():
#         sys.exit("Ledger file not found")

#     root   = Path(__file__).resolve().parents[1]
#     print(f"Reading ledger: {ledger}", flush=True)

#     pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
#     df     = pd.read_csv(ledger)
#     credit, debt, bank = classify(df)

#     total_rows = len(credit) + len(debt)
#     print(f"Rows kept after Done? filter: {total_rows}", flush=True)

#     if bank > 0:
#         debt.append(("BANK", bank))
#     elif bank < 0:
#         credit.append(("BANK", -bank))

#     tx = settle(credit, debt, soft=args.soft, hard=args.hard)
#     tx = cancel_cycles(tx)

#     # merge duplicates
#     merged = defaultdict(Decimal)
#     for fr, to, amt in tx:
#         merged[(fr, to)] += amt
#     tx = sorted([(fr, to, amt) for (fr, to), amt in merged.items()],
#                 key=lambda x: (x[0], x[1]))

#     tag_m = re.search(r"(\d{1,2}_\d{1,2}_\d{2})", ledger.stem)
#     tag   = tag_m.group(1) if tag_m else "output"
#     out   = root / "Transactions" / f"{tag}_transactions_v6.csv"
#     out.parent.mkdir(exist_ok=True)

#     with out.open("w", newline="") as f:
#         w = csv.writer(f)
#         w.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in tx:
#             fr_disp = fr.split(" @row")[0]
#             to_disp = to.split(" @row")[0]
#             w.writerow([
#                 fr_disp,
#                 to_disp,
#                 money_str(amt),
#                 method_string(to_disp, amt, pay_db)
#             ])

#     print(f"✅  Wrote {out}  ({len(tx)} transfers; "
#           f"soft cap={args.soft}, hard cap={args.hard})",
#           flush=True)

# if __name__ == "__main__":
#     main()












######### VERSION WHERE IF NO DEBTERS FOR PROFITTERS THEN BANK PAYS #########################






# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v6.py
# ──────────────────────────
# • Skips any ledger row with Done? == "Yes"
# • Greedy netting with soft/hard caps (--soft default 3, --hard default 4)
# • BANK overflow when soft cap is reached or when no creditors remain
# • 3-cycle cancellation
# • Verbose prints so you can follow progress
# """

# from __future__ import annotations
# import argparse, csv, re, sys
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple
# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# # ── tiny helpers ────────────────────────────────────────────────────────────
# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)
# def normal_forms(raw: str) -> List[str]:
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     out = [raw.strip().lower()]
#     if before: out.append(before.strip().lower())
#     if inside: out.append(inside.strip().lower())
#     return list(dict.fromkeys(out))

# def parse_money(v) -> Decimal:
#     if pd.isna(v):
#         return Decimal("0")
#     return Decimal(str(v).replace("$", "").replace(",", "").strip())

# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"

# # ── payment-method DB ───────────────────────────────────────────────────────
# def load_payment_db(path: Path) -> Dict[str, List[str]]:
#     if not path.exists():
#         return {}
#     df = pd.read_csv(path)
#     db: Dict[str, List[str]] = {}
#     for _, row in df.iterrows():
#         raw = row["Player Name"]
#         handles: List[str] = []
#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             lbl = col.strip().lower()
#             if lbl == "venmo"   and not val.startswith("@"):
#                 val = "@" + val
#             if lbl == "cashapp" and not val.startswith("$"):
#                 val = "$" + val
#             handles.append(f"{col.strip()}: {val}")
#         for k in normal_forms(str(raw)):
#             db.setdefault(k, [])
#             for h in handles:
#                 if h not in db[k]:
#                     db[k].append(h)
#     return db

# def method_string(name: str, amt: Decimal, db: Dict[str, List[str]]) -> str:
#     if name == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"
#     for k in normal_forms(name):
#         if k in db:
#             return (
#                 f"Pay user ${money_str(amt)} on " +
#                 ", ".join(f"({h})" for h in db[k])
#             )
#     return f"Pay user ${money_str(amt)} on (Venmo: )"

# # ── classification (skips Done? == Yes) ─────────────────────────────────────
# def classify(df: pd.DataFrame) -> Tuple[
#         List[Tuple[str, Decimal]],
#         List[Tuple[str, Decimal]],
#         Decimal]:
#     creditors: List[Tuple[str, Decimal]] = []
#     debtors:   List[Tuple[str, Decimal]] = []
#     bank = Decimal("0")

#     for idx, row in df.iterrows():
#         if str(row.get("Done?", "")).strip().lower() == "yes":
#             continue

#         disp = str(row["Player Name"]).strip()
#         node = f"{disp} @row{idx}"

#         cred_flag = str(row["Credit?"]).strip().lower()
#         received  = parse_money(row.get("$ Received", 0))
#         ending    = parse_money(row.get("Ending Stack", 0))
#         pl        = parse_money(row.get("P/L Player", 0))
#         send_out  = parse_money(row.get("Send Out", 0))
#         sent_col  = parse_money(row.get("$ Sent", 0))

#         if cred_flag != "yes":
#             bank += received
#             if ending > 0:
#                 creditors.append((node, sent_col))
#         else:
#             if pl < 0:
#                 debtors.append((node, abs(send_out)))
#             elif pl > 0:
#                 creditors.append((node, sent_col))

#     return creditors, debtors, bank

# # ── settlement with soft/hard caps ──────────────────────────────────────────
# Transfer = Tuple[str, str, Decimal]

# def settle(
#     creditors_in: List[Tuple[str, Decimal]],
#     debtors_in:   List[Tuple[str, Decimal]],
#     soft: int,
#     hard: int
# ) -> List[Transfer]:
#     creditors = deque(sorted(creditors_in, key=lambda x: x[1], reverse=True))
#     debtors   = sorted(debtors_in,    key=lambda x: x[1], reverse=True)

#     transfers: List[Transfer] = []
#     outcnt = defaultdict(int)

#     for debtor, owe in debtors:
#         while owe > 0:
#             # no more than `hard` transfers
#             if outcnt[debtor] >= hard:
#                 raise RuntimeError(f"{debtor} exceeded hard cap of {hard}")

#             # if at or past soft cap → dump remainder to BANK
#             if outcnt[debtor] >= soft:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break

#             # if no creditors remain, dump remainder to BANK
#             if not creditors:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break

#             # normal greedy payment to largest creditor
#             cred, need = creditors[0]
#             pay = min(owe, need)

#             transfers.append((debtor, cred, pay))
#             outcnt[debtor] += 1
#             owe -= pay
#             need -= pay

#             if need == 0:
#                 creditors.popleft()
#             else:
#                 creditors[0] = (cred, need)

#     # BANK pays off any remaining creditors
#     for cred, need in creditors:
#         if need > 0:
#             transfers.append(("BANK", cred, need))

#     return transfers

# # ── 3-cycle cancellation ───────────────────────────────────────────────────
# def cancel_cycles(ts: List[Transfer]) -> List[Transfer]:
#     graph = defaultdict(Decimal)
#     for fr, to, amt in ts:
#         if fr != to and amt:
#             graph[(fr, to)] += amt

#     changed = True
#     while changed:
#         changed = False
#         for (a, b), ab in list(graph.items()):
#             if a == "BANK" or b == "BANK":
#                 continue
#             for (b2, c), bc in list(graph.items()):
#                 if b2 != b or c == "BANK":
#                     continue
#                 if (c, a) in graph:
#                     ca = graph[(c, a)]
#                     x = min(ab, bc, ca)
#                     for e in [(a, b), (b, c), (c, a)]:
#                         graph[e] -= x
#                         if graph[e] == 0:
#                             del graph[e]
#                     changed = True
#                     break
#             if changed:
#                 break

#     return [(fr, to, amt) for (fr, to), amt in graph.items()]

# # ── driver ──────────────────────────────────────────────────────────────────
# def main() -> None:
#     p = argparse.ArgumentParser()
#     p.add_argument("--csv",  required=True,
#                    help="Path to ledger CSV (Ledger Data/…)") 
#     p.add_argument("--soft", type=int, default=3,
#                    help="Soft cap on outgoing transfers (default 3)")
#     p.add_argument("--hard", type=int, default=4,
#                    help="Hard cap on outgoing transfers (default 4)")
#     args = p.parse_args()

#     ledger = Path(args.csv).expanduser()
#     if not ledger.exists():
#         sys.exit("Ledger file not found")

#     root   = Path(__file__).resolve().parents[1]
#     print(f"Reading ledger: {ledger}", flush=True)

#     pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
#     df     = pd.read_csv(ledger)
#     credit, debt, bank = classify(df)

#     total_rows = len(credit) + len(debt)
#     print(f"Rows kept after Done? filter: {total_rows}", flush=True)

#     if bank > 0:
#         debt.append(("BANK", bank))
#     elif bank < 0:
#         credit.append(("BANK", -bank))

#     tx = settle(credit, debt, soft=args.soft, hard=args.hard)
#     tx = cancel_cycles(tx)

#     # merge duplicates
#     merged = defaultdict(Decimal)
#     for fr, to, amt in tx:
#         merged[(fr, to)] += amt
#     tx = sorted([(fr, to, amt) for (fr, to), amt in merged.items()],
#                 key=lambda x: (x[0], x[1]))

#     tag_m = re.search(r"(\d{1,2}_\d{1,2}_\d{2})", ledger.stem)
#     tag   = tag_m.group(1) if tag_m else "output"
#     out   = root / "Transactions" / f"{tag}_transactions_v6.csv"
#     out.parent.mkdir(exist_ok=True)

#     with out.open("w", newline="") as f:
#         w = csv.writer(f)
#         w.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in tx:
#             fr_disp = fr.split(" @row")[0]
#             to_disp = to.split(" @row")[0]
#             w.writerow([
#                 fr_disp,
#                 to_disp,
#                 money_str(amt),
#                 method_string(to_disp, amt, pay_db)
#             ])

#     print(f"✅  Wrote {out}  ({len(tx)} transfers; "
#           f"soft cap={args.soft}, hard cap={args.hard})",
#           flush=True)

# if __name__ == "__main__":
#     main()




















########### MOST RECENT WORKING VERSION ########################





# """
# Backend/payoutSystem_v6.py
# ──────────────────────────
# • Skips any ledger row with Done? == "Yes"
# • Greedy netting with soft/hard caps (--soft default 3, --hard default 4)
# • BANK overflow when soft cap is reached or when no creditors remain
# • 3-cycle cancellation
# • Verbose prints so you can follow progress
# """

# from __future__ import annotations
# import argparse, csv, re, sys
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple
# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# # ── tiny helpers ────────────────────────────────────────────────────────────
# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)

# def normal_forms(raw: str) -> List[str]:
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     out = [raw.strip().lower()]
#     if before: out.append(before.strip().lower())
#     if inside: out.append(inside.strip().lower())
#     return list(dict.fromkeys(out))


# def parse_money(v) -> Decimal:
#     if pd.isna(v):
#         return Decimal("0")
#     return Decimal(str(v).replace("$", "").replace(",", "").strip())


# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"

# # ── payment-method DB ───────────────────────────────────────────────────────
# def load_payment_db(path: Path) -> Dict[str, List[str]]:
#     if not path.exists():
#         return {}
#     df = pd.read_csv(path)
#     db: Dict[str, List[str]] = {}
#     for _, row in df.iterrows():
#         raw = row["Player Name"]
#         handles: List[str] = []
#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             lbl = col.strip().lower()
#             if lbl == "venmo"   and not val.startswith("@"): val = "@" + val
#             if lbl == "cashapp" and not val.startswith("$"): val = "$" + val
#             handles.append(f"{col.strip()}: {val}")
#         for k in normal_forms(str(raw)):
#             db.setdefault(k, [])
#             for h in handles:
#                 if h not in db[k]:
#                     db[k].append(h)
#     return db


# def method_string(name: str, amt: Decimal, db: Dict[str, List[str]]) -> str:
#     if name == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"
#     for k in normal_forms(name):
#         if k in db:
#             return (
#                 f"Pay user ${money_str(amt)} on " +
#                 ", ".join(f"({h})" for h in db[k])
#             )
#     return f"Pay user ${money_str(amt)} on (Venmo: )"

# # ── classification (skips Done? == Yes) ─────────────────────────────────────
# def classify(df: pd.DataFrame) -> Tuple[List[Tuple[str, Decimal]], List[Tuple[str, Decimal]], Decimal]:
#     creditors: List[Tuple[str, Decimal]] = []
#     debtors:   List[Tuple[str, Decimal]] = []
#     bank = Decimal("0")

#     for idx, row in df.iterrows():
#         if str(row.get("Done?", "")).strip().lower() == "yes":
#             continue

#         disp = str(row["Player Name"]).strip()
#         node = f"{disp} @row{idx}"

#         cred_flag = str(row["Credit?"]).strip().lower()
#         received  = parse_money(row.get("$ Received", 0))
#         ending    = parse_money(row.get("Ending Stack", 0))
#         pl        = parse_money(row.get("P/L Player", 0))
#         send_out  = parse_money(row.get("Send Out", 0))
#         sent_col  = parse_money(row.get("$ Sent", 0))

#         if cred_flag != "yes":
#             bank += received
#             if ending > 0:
#                 creditors.append((node, sent_col))
#         else:
#             if pl < 0:
#                 debtors.append((node, abs(send_out)))
#             elif pl > 0:
#                 creditors.append((node, sent_col))

#     return creditors, debtors, bank

# # ── settlement with soft/hard caps and BANK-last fix ─────────────────────────
# Transfer = Tuple[str, str, Decimal]

# def settle(
#     creditors_in: List[Tuple[str, Decimal]],
#     debtors_in:   List[Tuple[str, Decimal]],
#     soft: int,
#     hard: int
# ) -> List[Transfer]:
#     # sort creditors largest→smallest
#     creditors = deque(sorted(creditors_in, key=lambda x: x[1], reverse=True))
#     # ensure BANK debtor is last: sort by (is_bank, -amount)
#     debtors = sorted(
#         debtors_in,
#         key=lambda x: (x[0] == "BANK", -x[1])
#     )

#     transfers: List[Transfer] = []
#     outcnt = defaultdict(int)

#     for debtor, owe in debtors:
#         while owe > 0:
#             if outcnt[debtor] >= hard:
#                 raise RuntimeError(f"{debtor} exceeded hard cap of {hard}")

#             if outcnt[debtor] >= soft:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break

#             if not creditors:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break

#             cred, need = creditors[0]
#             pay = min(owe, need)

#             transfers.append((debtor, cred, pay))
#             outcnt[debtor] += 1
#             owe -= pay
#             need -= pay

#             if need == 0:
#                 creditors.popleft()
#             else:
#                 creditors[0] = (cred, need)

#     # BANK pays remaining creditors
#     for cred, need in creditors:
#         if need > 0:
#             transfers.append(("BANK", cred, need))

#     return transfers

# # ── 3-cycle cancellation ───────────────────────────────────────────────────
# def cancel_cycles(ts: List[Transfer]) -> List[Transfer]:
#     graph = defaultdict(Decimal)
#     for fr, to, amt in ts:
#         if fr != to and amt:
#             graph[(fr, to)] += amt

#     changed = True
#     while changed:
#         changed = False
#         for (a, b), ab in list(graph.items()):
#             if a == "BANK" or b == "BANK":
#                 continue
#             for (b2, c), bc in list(graph.items()):
#                 if b2 != b or c == "BANK":
#                     continue
#                 if (c, a) in graph:
#                     ca = graph[(c, a)]
#                     x = min(ab, bc, ca)
#                     for e in [(a, b), (b, c), (c, a)]:
#                         graph[e] -= x
#                         if graph[e] == 0:
#                             del graph[e]
#                     changed = True
#                     break
#             if changed:
#                 break

#     return [(fr, to, amt) for (fr, to), amt in graph.items()]

# # ── driver ──────────────────────────────────────────────────────────────────
# def main() -> None:
#     p = argparse.ArgumentParser()
#     p.add_argument("--csv",  required=True,
#                    help="Path to ledger CSV (Ledger Data/…)") 
#     p.add_argument("--soft", type=int, default=3,
#                    help="Soft cap on outgoing transfers (default 3)")
#     p.add_argument("--hard", type=int, default=4,
#                    help="Hard cap on outgoing transfers (default 4)")
#     args = p.parse_args()

#     ledger = Path(args.csv).expanduser()
#     if not ledger.exists():
#         sys.exit("Ledger file not found")

#     root   = Path(__file__).resolve().parents[1]
#     print(f"Reading ledger: {ledger}", flush=True)

#     pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
#     df     = pd.read_csv(ledger)
#     credit, debt, bank = classify(df)

#     total_rows = len(credit) + len(debt)
#     print(f"Rows kept after Done? filter: {total_rows}", flush=True)

#     if bank > 0:
#         debt.append(("BANK", bank))
#     elif bank < 0:
#         credit.append(("BANK", -bank))

#     tx = settle(credit, debt, soft=args.soft, hard=args.hard)
#     tx = cancel_cycles(tx)

#     # merge duplicates
#     merged = defaultdict(Decimal)
#     for fr, to, amt in tx:
#         merged[(fr, to)] += amt
#     tx = sorted([(fr, to, amt) for (fr, to), amt in merged.items()],
#                 key=lambda x: (x[0], x[1]))

#     tag_m = re.search(r"(\d{1,2}_\d{1,2}_\d{2})", ledger.stem)
#     tag   = tag_m.group(1) if tag_m else "output"
#     out   = root / "Transactions" / f"{tag}_transactions_v6.csv"
#     out.parent.mkdir(exist_ok=True)

#     with out.open("w", newline="") as f:
#         w = csv.writer(f)
#         w.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in tx:
#             fr_disp = fr.split(" @row")[0]
#             to_disp = to.split(" @row")[0]
#             w.writerow([
#                 fr_disp,
#                 to_disp,
#                 money_str(amt),
#                 method_string(to_disp, amt, pay_db)
#             ])

#     print(f"✅  Wrote {out}  ({len(tx)} transfers; "
#           f"soft cap={args.soft}, hard cap={args.hard})",
#           flush=True)

# if __name__ == "__main__":
#     main()





















############## same version but can now adjust ledger data file names#####################







# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v6.py
# ──────────────────────────
# • Skips any ledger row with Done? == "Yes"
# • Greedy netting with soft/hard caps (--soft default 3, --hard default 4)
# • BANK overflow when soft cap is reached or when no creditors remain
# • 3-cycle cancellation
# • Verbose prints so you can follow progress
# • Accepts arbitrary ledger filenames (no date-format enforced)
# """

# from __future__ import annotations
# import argparse, csv, re, sys
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple
# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# # ── tiny helpers ────────────────────────────────────────────────────────────
# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)

# def normal_forms(raw: str) -> List[str]:
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     out = [raw.strip().lower()]
#     if before: out.append(before.strip().lower())
#     if inside: out.append(inside.strip().lower())
#     return list(dict.fromkeys(out))

# def parse_money(v) -> Decimal:
#     if pd.isna(v):
#         return Decimal("0")
#     return Decimal(str(v).replace("$", "").replace(",", "").strip())

# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"

# # ── payment-method DB ───────────────────────────────────────────────────────
# def load_payment_db(path: Path) -> Dict[str, List[str]]:
#     if not path.exists():
#         return {}
#     df = pd.read_csv(path)
#     db: Dict[str, List[str]] = {}
#     for _, row in df.iterrows():
#         raw = row["Player Name"]
#         handles: List[str] = []
#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             lbl = col.strip().lower()
#             if lbl == "venmo"   and not val.startswith("@"): val = "@" + val
#             if lbl == "cashapp" and not val.startswith("$"): val = "$" + val
#             handles.append(f"{col.strip()}: {val}")
#         for k in normal_forms(str(raw)):
#             db.setdefault(k, [])
#             for h in handles:
#                 if h not in db[k]:
#                     db[k].append(h)
#     return db

# def method_string(name: str, amt: Decimal, db: Dict[str, List[str]]) -> str:
#     if name == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"
#     for k in normal_forms(name):
#         if k in db:
#             return (
#                 f"Pay user ${money_str(amt)} on " +
#                 ", ".join(f"({h})" for h in db[k])
#             )
#     return f"Pay user ${money_str(amt)} on (Venmo: )"

# # ── classification (skips Done? == Yes) ─────────────────────────────────────
# def classify(df: pd.DataFrame) -> Tuple[List[Tuple[str, Decimal]], List[Tuple[str, Decimal]], Decimal]:
#     creditors: List[Tuple[str, Decimal]] = []
#     debtors:   List[Tuple[str, Decimal]] = []
#     bank = Decimal("0")
#     for idx, row in df.iterrows():
#         if str(row.get("Done?", "")).strip().lower() == "yes":
#             continue
#         disp = str(row["Player Name"]).strip()
#         node = f"{disp} @row{idx}"
#         cred_flag = str(row["Credit?"]).strip().lower()
#         received  = parse_money(row.get("$ Received", 0))
#         ending    = parse_money(row.get("Ending Stack", 0))
#         pl        = parse_money(row.get("P/L Player", 0))
#         send_out  = parse_money(row.get("Send Out", 0))
#         sent_col  = parse_money(row.get("$ Sent", 0))
#         if cred_flag != "yes":
#             bank += received
#             if ending > 0:
#                 creditors.append((node, sent_col))
#         else:
#             if pl < 0:
#                 debtors.append((node, abs(send_out)))
#             elif pl > 0:
#                 creditors.append((node, sent_col))
#     return creditors, debtors, bank

# # ── settlement with soft/hard caps and BANK-last fix ─────────────────────────
# Transfer = Tuple[str, str, Decimal]
# def settle(
#     creditors_in: List[Tuple[str, Decimal]],
#     debtors_in:   List[Tuple[str, Decimal]],
#     soft: int,
#     hard: int
# ) -> List[Transfer]:
#     creditors = deque(sorted(creditors_in, key=lambda x: x[1], reverse=True))
#     debtors = sorted(
#         debtors_in,
#         key=lambda x: (x[0] == "BANK", -x[1])
#     )
#     transfers: List[Transfer] = []
#     outcnt = defaultdict(int)
#     for debtor, owe in debtors:
#         while owe > 0:
#             if outcnt[debtor] >= hard:
#                 raise RuntimeError(f"{debtor} exceeded hard cap of {hard}")
#             if outcnt[debtor] >= soft:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break
#             if not creditors:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 owe = Decimal("0")
#                 break
#             cred, need = creditors[0]
#             pay = min(owe, need)
#             transfers.append((debtor, cred, pay))
#             outcnt[debtor] += 1
#             owe -= pay
#             need -= pay
#             if need == 0:
#                 creditors.popleft()
#             else:
#                 creditors[0] = (cred, need)
#     for cred, need in creditors:
#         if need > 0:
#             transfers.append(("BANK", cred, need))
#     return transfers

# # ── 3-cycle cancellation ───────────────────────────────────────────────────
# def cancel_cycles(ts: List[Transfer]) -> List[Transfer]:
#     graph = defaultdict(Decimal)
#     for fr, to, amt in ts:
#         if fr != to and amt:
#             graph[(fr, to)] += amt
#     changed = True
#     while changed:
#         changed = False
#         for (a, b), ab in list(graph.items()):
#             if a == "BANK" or b == "BANK":
#                 continue
#             for (b2, c), bc in list(graph.items()):
#                 if b2 != b or c == "BANK":
#                     continue
#                 if (c, a) in graph:
#                     ca = graph[(c, a)]
#                     x = min(ab, bc, ca)
#                     for e in [(a, b), (b, c), (c, a)]:
#                         graph[e] -= x
#                         if graph[e] == 0:
#                             del graph[e]
#                     changed = True
#                     break
#             if changed:
#                 break
#     return [(fr, to, amt) for (fr, to), amt in graph.items()]

# # ── driver ──────────────────────────────────────────────────────────────────
# def main() -> None:
#     p = argparse.ArgumentParser()
#     p.add_argument("--csv",  required=True,
#                    help="Path to ledger CSV (any filename, no date format required)")
#     p.add_argument("--soft", type=int, default=3,
#                    help="Soft cap on outgoing transfers (default 3)")
#     p.add_argument("--hard", type=int, default=4,
#                    help="Hard cap on outgoing transfers (default 4)")
#     args = p.parse_args()

#     ledger = Path(args.csv).expanduser()
#     if not ledger.exists():
#         sys.exit("Ledger file not found")

#     root   = Path(__file__).resolve().parents[1]
#     print(f"Reading ledger: {ledger}", flush=True)

#     pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
#     df     = pd.read_csv(ledger)
#     credit, debt, bank = classify(df)

#     total_rows = len(credit) + len(debt)
#     print(f"Rows kept after Done? filter: {total_rows}", flush=True)

#     if bank > 0:
#         debt.append(("BANK", bank))
#     elif bank < 0:
#         credit.append(("BANK", -bank))

#     tx = settle(credit, debt, soft=args.soft, hard=args.hard)
#     tx = cancel_cycles(tx)

#     # merge duplicates and sort
#     merged = defaultdict(Decimal)
#     for fr, to, amt in tx:
#         merged[(fr, to)] += amt
#     tx = sorted([(fr, to, amt) for (fr, to), amt in merged.items()],
#                 key=lambda x: (x[0], x[1]))

#     # use the filename stem directly for output
#     tag = ledger.stem
#     out = root / "Transactions" / f"{tag}_transactions_v6.csv"
#     out.parent.mkdir(exist_ok=True)

#     with out.open("w", newline="") as f:
#         w = csv.writer(f)
#         w.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in tx:
#             fr_disp = fr.split(" @row")[0]
#             to_disp = to.split(" @row")[0]
#             w.writerow([
#                 fr_disp,
#                 to_disp,
#                 money_str(amt),
#                 method_string(to_disp, amt, pay_db)
#             ])

#     print(f"✅  Wrote {out}  ({len(tx)} transfers; "
#           f"soft cap={args.soft}, hard cap={args.hard})",
#           flush=True)

# if __name__ == "__main__":
#     main()









################### CANCELS CYCLES WITHIN PLAYERS WHO PLAYED TWICE IN A SESSION #####################
##################### DOES NOT GIVE PAYMENT METHODS FOR ALL PLAYERS################




# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v6.py
# ──────────────────────────
# • Ignores rows whose Done? == "Yes".
# • Combines multiple rows for the same player into one net balance.
# • Greedy netting with --soft / --hard caps (defaults 3 / 4).
# • BANK processed last; covers any leftover creditors.
# • 3-cycle cancellation after settlement.
# """

# from __future__ import annotations
# import argparse, csv, sys, re
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple
# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# # ─────────────────────── helpers ────────────────────────────────────────────
# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)

# def canonical(raw: str) -> str:
#     """Use the part before '(' if present, else full stripped name (lower-case)."""
#     m = NAME_RE.match(raw)
#     return (m.group(1) if m else raw).strip().lower()

# def parse_money(x) -> Decimal:
#     if pd.isna(x):
#         return Decimal("0")
#     return Decimal(str(x).replace("$", "").replace(",", "").strip())

# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"

# # ───────────────── payment-method DB ────────────────────────────────────────
# def load_payment_db(path: Path) -> Dict[str, List[str]]:
#     if not path.exists():
#         return {}
#     df = pd.read_csv(path)
#     db: Dict[str, List[str]] = {}
#     for _, row in df.iterrows():
#         raw = str(row["Player Name"]).strip()
#         handles: List[str] = []
#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             tag = col.strip()
#             if tag.lower() == "venmo"   and not val.startswith("@"): val = "@" + val
#             if tag.lower() == "cashapp" and not val.startswith("$"): val = "$" + val
#             handles.append(f"{tag}: {val}")
#         key = canonical(raw)
#         db.setdefault(key, []).extend([h for h in handles if h not in db[key]])
#     return db

# def method_string(name_display: str, amt: Decimal, db) -> str:
#     if name_display == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"
#     key = canonical(name_display)
#     handles = db.get(key, ["Venmo: "])
#     return f"Pay user ${money_str(amt)} on " + ", ".join(f"({h})" for h in handles)

# # ────────────────── classify & aggregate rows ───────────────────────────────
# def classify(df: pd.DataFrame):
#     """
#     Returns creditors[], debtors[], bank_balance.
#     Duplicated names are netted into a single balance.
#     """
#     net: Dict[str, Decimal]       = defaultdict(Decimal)   # canonical → net $
#     display_name: Dict[str, str]  = {}                    # canonical → first display
#     bank = Decimal("0")

#     for _, row in df.iterrows():
#         if str(row.get("Done?", "")).strip().lower() == "yes":
#             continue

#         disp = str(row["Player Name"]).strip()
#         key  = canonical(disp)
#         display_name.setdefault(key, disp)

#         credit_flag = str(row["Credit?"]).strip().lower()
#         received    = parse_money(row.get("$ Received", 0))
#         ending      = parse_money(row.get("Ending Stack", 0))
#         pl          = parse_money(row.get("P/L Player", 0))
#         send_out    = parse_money(row.get("Send Out", 0))
#         sent_col    = parse_money(row.get("$ Sent", 0))

#         if credit_flag != "yes":                # NOT ledgered
#             bank += received
#             if ending > 0:                      # cashed chips
#                 net[key] += sent_col
#         else:                                   # LEDGERED
#             if pl < 0:
#                 net[key] -= abs(send_out)
#             elif pl > 0:
#                 net[key] += sent_col

#     creditors, debtors = [], []
#     for k, bal in net.items():
#         if bal > 0:
#             creditors.append((display_name[k], bal))
#         elif bal < 0:
#             debtors.append((display_name[k], abs(bal)))

#     return creditors, debtors, bank

# # ───────────────── settlement (BANK last) ───────────────────────────────────
# Transfer = Tuple[str, str, Decimal]

# def settle(creditors_in, debtors_in, soft, hard) -> List[Transfer]:
#     creditors = deque(sorted(creditors_in, key=lambda x: x[1], reverse=True))
#     debtors   = sorted(debtors_in, key=lambda x: (x[0] == "BANK", -x[1]))

#     outcnt = defaultdict(int)
#     transfers: List[Transfer] = []

#     for debtor, owe in debtors:
#         while owe > 0:
#             if outcnt[debtor] >= hard:
#                 raise RuntimeError(f"{debtor} exceeded hard cap {hard}")

#             if outcnt[debtor] >= soft or not creditors:
#                 transfers.append((debtor, "BANK", owe))
#                 outcnt[debtor] += 1
#                 break

#             cred, need = creditors[0]
#             pay = min(owe, need)

#             transfers.append((debtor, cred, pay))
#             outcnt[debtor] += 1
#             owe  -= pay
#             need -= pay

#             if need == 0:
#                 creditors.popleft()
#             else:
#                 creditors[0] = (cred, need)

#     for cred, need in creditors:
#         if need > 0:
#             transfers.append(("BANK", cred, need))
#     return transfers

# # ───────────────── 3-cycle cancellation ────────────────────────────────────
# def cancel_cycles(txs: List[Transfer]) -> List[Transfer]:
#     g = defaultdict(Decimal)
#     for fr, to, amt in txs:
#         if fr != to and amt:
#             g[(fr, to)] += amt
#     changed = True
#     while changed:
#         changed = False
#         for (a, b), ab in list(g.items()):
#             if a == "BANK" or b == "BANK":
#                 continue
#             for (b2, c), bc in list(g.items()):
#                 if b2 != b or c == "BANK":
#                     continue
#                 if (c, a) in g:
#                     ca = g[(c, a)]
#                     x = min(ab, bc, ca)
#                     for e in [(a, b), (b, c), (c, a)]:
#                         g[e] -= x
#                         if g[e] == 0:
#                             del g[e]
#                     changed = True
#                     break
#             if changed:
#                 break
#     return [(fr, to, amt) for (fr, to), amt in g.items()]

# # ───────────────────────────── driver ───────────────────────────────────────
# def main() -> None:
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--csv", required=True,
#                     help="Path to ledger CSV (any filename)")
#     ap.add_argument("--soft", type=int, default=3, help="Soft cap (default 3)")
#     ap.add_argument("--hard", type=int, default=4, help="Hard cap (default 4)")
#     args = ap.parse_args()

#     ledger = Path(args.csv).expanduser()
#     if not ledger.exists():
#         sys.exit("Ledger file not found")

#     root = Path(__file__).resolve().parents[1]
#     pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")

#     df = pd.read_csv(ledger)
#     creditors, debtors, bank = classify(df)

#     if bank > 0:
#         debtors.append(("BANK", bank))
#     elif bank < 0:
#         creditors.append(("BANK", -bank))

#     transfers = cancel_cycles(
#         settle(creditors, debtors, soft=args.soft, hard=args.hard)
#     )

#     merged = defaultdict(Decimal)
#     for fr, to, amt in transfers:
#         merged[(fr, to)] += amt
#     transfers = sorted([(fr, to, amt) for (fr, to), amt in merged.items()],
#                        key=lambda x: (x[0], x[1]))

#     out = root / "Transactions" / f"{ledger.stem}_transactions_v6.csv"
#     out.parent.mkdir(exist_ok=True)

#     with out.open("w", newline="") as f:
#         w = csv.writer(f)
#         w.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in transfers:
#             w.writerow([
#                 fr,
#                 to,
#                 money_str(amt),
#                 method_string(to, amt, pay_db)
#             ])

#     print(f"✅  Wrote {out}  ({len(transfers)} transfers; "
#           f"soft={args.soft}, hard={args.hard})", flush=True)

# if __name__ == "__main__":
#     main()












#!/usr/bin/env python3
"""
Backend/payoutSystem_v6.py
──────────────────────────
• Skips rows whose Done? == "Yes".
• Combines duplicate players into one net balance.
• Greedy settlement with --soft / --hard caps (defaults 3 / 4).
• BANK pays residuals; 3-cycle cancellation after settlement.
• NEW alias logic:
    Payment Methods 'Player Name' can be "(alias1), (Alias2)" etc.
    ─ first token before '(' and every individual (…) are aliases.
    Ledger 'Player Name':
    ─ first token + every (…) alias.
    Case-insensitive, leading '.' or '@' ignored.
"""

from __future__ import annotations
import argparse, csv, sys, re
from pathlib import Path
from collections import defaultdict, deque
from decimal import Decimal, getcontext
from typing import Dict, List, Tuple
import pandas as pd

getcontext().prec = 28
CENT = Decimal("0.01")

# ───────────────────────── alias helpers ────────────────────────────────────
PAR_RE = re.compile(r"\(([^)]+)\)")       # grab text inside every ( … )
TOK_RE = re.compile(r"^\s*([^\s(]+)")     # first token in ledger string

def clean(token: str) -> str:
    """lower-case and strip leading '.' or '@'."""
    return token.lstrip(".@").strip().lower()

def aliases_from_pm(raw: str) -> List[str]:
    """
    Payment Methods ‘Player Name’ field, e.g.
        "(frankie2119), (Frankie)"
        "(.joonga) (joonga)"
    """
    raw = str(raw).strip()
    aliases: List[str] = []

    # part before first '(' if any
    head = raw.split("(", 1)[0].strip(" ,")
    if head:
        alias = clean(head)
        if alias:
            aliases.append(alias)

    # every (…) group
    for grp in PAR_RE.findall(raw):
        alias = clean(grp)
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases

def aliases_from_ledger(raw: str) -> List[str]:
    """
    Ledger ‘Player Name’ field, e.g. "CSizzle (siz)"
    returns ["csizzle", "siz"]
    """
    raw = str(raw).strip()
    aliases: List[str] = []

    # first token
    m = TOK_RE.match(raw)
    if m:
        alias = clean(m.group(1))
        if alias:
            aliases.append(alias)

    # aliases inside (...)
    for grp in PAR_RE.findall(raw):
        alias = clean(grp)
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases

def parse_money(x) -> Decimal:
    if pd.isna(x):
        return Decimal("0")
    return Decimal(str(x).replace("$", "").replace(",", "").strip())

def money_str(x: Decimal) -> str:
    return f"{x.quantize(CENT)}"

# ───────────────── payment-method DB ────────────────────────────────────────
def load_payment_db(csv_path: Path) -> Dict[str, List[str]]:
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path)
    db: Dict[str, List[str]] = {}

    for _, row in df.iterrows():
        raw_name = str(row["Player Name"]).strip()

        # gather handles
        handles: List[str] = []
        for col, val in row.items():
            if col == "Player Name":
                continue
            val = str(val).strip()
            if not val or val.lower() == "nan":
                continue
            lbl = col.strip()
            if lbl.lower() == "venmo"   and not val.startswith("@"): val = "@" + val
            if lbl.lower() == "cashapp" and not val.startswith("$"): val = "$" + val
            handles.append(f"{lbl}: {val}")

        for alias in aliases_from_pm(raw_name):
            db.setdefault(alias, [])
            for h in handles:
                if h not in db[alias]:
                    db[alias].append(h)
    return db

def method_string(name_display: str, amt: Decimal, db: Dict[str, List[str]]) -> str:
    if name_display == "BANK":
        return f"Internal bank transfer of ${money_str(amt)}"
    for alias in aliases_from_ledger(name_display):
        if alias in db:
            handles = db[alias]
            break
    else:
        handles = ["Venmo: "]
    return f"Pay user ${money_str(amt)} on " + ", ".join(f"({h})" for h in handles)

# ────────────────── classify & aggregate rows ───────────────────────────────
def classify(df: pd.DataFrame):
    net, disp = defaultdict(Decimal), {}
    bank = Decimal("0")

    for _, row in df.iterrows():
        if str(row.get("Done?", "")).strip().lower() == "yes":
            continue
        name = str(row["Player Name"]).strip()
        key  = aliases_from_ledger(name)[0]   # canonical
        disp.setdefault(key, name)

        credit_flag = str(row["Credit?"]).strip().lower()
        received = parse_money(row.get("$ Received", 0))
        ending   = parse_money(row.get("Ending Stack", 0))
        pl       = parse_money(row.get("P/L Player", 0))
        send_out = parse_money(row.get("Send Out", 0))
        sent_col = parse_money(row.get("$ Sent", 0))

        if credit_flag != "yes":
            bank += received
            if ending > 0:
                net[key] += sent_col
        else:
            if pl < 0:   net[key] -= abs(send_out)
            elif pl > 0: net[key] += sent_col

    cred, debt = [], []
    for k, bal in net.items():
        if bal > 0:  cred.append((disp[k], bal))
        elif bal < 0: debt.append((disp[k], abs(bal)))
    return cred, debt, bank

# ───────────────── settlement + cycles (unchanged) ──────────────────────────
Transfer = Tuple[str, str, Decimal]

def settle(creditors, debtors, soft, hard):
    creditors = deque(sorted(creditors, key=lambda x: x[1], reverse=True))
    debtors   = sorted(debtors, key=lambda x: (x[0]=="BANK", -x[1]))
    outcnt, txs = defaultdict(int), []

    for debtor, owe in debtors:
        while owe>0:
            if outcnt[debtor] >= hard:
                raise RuntimeError(f"{debtor} exceeded hard cap {hard}")
            if outcnt[debtor] >= soft or not creditors:
                txs.append((debtor,"BANK",owe)); outcnt[debtor]+=1; break
            cred,need = creditors[0]
            pay=min(owe,need)
            txs.append((debtor,cred,pay)); outcnt[debtor]+=1
            owe-=pay; need-=pay
            if need==0: creditors.popleft()
            else: creditors[0]=(cred,need)
    for cred,need in creditors:
        if need>0: txs.append(("BANK",cred,need))
    return txs

def cancel_cycles(txs):
    g=defaultdict(Decimal)
    for fr,to,amt in txs:
        if fr!=to and amt: g[(fr,to)]+=amt
    changed=True
    while changed:
        changed=False
        for (a,b),ab in list(g.items()):
            if a=="BANK" or b=="BANK": continue
            for (b2,c),bc in list(g.items()):
                if b2!=b or c=="BANK": continue
                if (c,a) in g:
                    ca=g[(c,a)]; x=min(ab,bc,ca)
                    for e in [(a,b),(b,c),(c,a)]:
                        g[e]-=x
                        if g[e]==0: del g[e]
                    changed=True; break
            if changed: break
    return [(fr,to,amt) for (fr,to),amt in g.items()]

# ───────────────────────────── driver ───────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Ledger CSV")
    ap.add_argument("--soft", type=int, default=3)
    ap.add_argument("--hard", type=int, default=4)
    args = ap.parse_args()

    ledger = Path(args.csv).expanduser()
    if not ledger.exists(): sys.exit("Ledger not found")

    root   = Path(__file__).resolve().parents[1]
    pay_db = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
    df     = pd.read_csv(ledger)

    creditors, debtors, bank = classify(df)
    if bank>0:  debtors.append(("BANK", bank))
    elif bank<0: creditors.append(("BANK", -bank))

    transfers = cancel_cycles(settle(creditors, debtors, args.soft, args.hard))

    merged=defaultdict(Decimal)
    for fr,to,amt in transfers: merged[(fr,to)]+=amt
    transfers = sorted([(fr,to,amt) for (fr,to),amt in merged.items()],
                       key=lambda x:(x[0],x[1]))

    out = root / "Transactions" / f"{ledger.stem}_transactions_v6.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="") as f:
        w=csv.writer(f); w.writerow(["From","To","Amount","Method"])
        for fr,to,amt in transfers:
            w.writerow([fr,to,money_str(amt),method_string(to, amt, pay_db)])

    print(f"✅  Wrote {out} ({len(transfers)} transfers; soft={args.soft}, hard={args.hard})")

if __name__ == "__main__":
    main()
