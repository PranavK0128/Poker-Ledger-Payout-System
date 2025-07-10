# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v7.py
# ──────────────────────────
# • Treats every ledger row as its own node (rebuy ≠ original stack).
# • Greedy largest-debtor ↔ largest-creditor matching.
# • Hard cap: **3 outgoing transfers** per ledger row.
# • Overflow always goes to BANK, which then fans out to creditors.
# • 3-cycle cancellation removes round-robin edges.
# • Name-normalisation makes PAYMENT-METHOD lookup *case-insensitive* and
#   ignores/uses parentheses intelligently, so all handles appear.
# • No rounding – exact cents preserved.
# """

# from __future__ import annotations

# import argparse, csv, re
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple

# import pandas as pd

# getcontext().prec = 28           # plenty for cent-level accuracy
# CENT = Decimal("0.01")

# # ─────────────────────────── helper utilities ────────────────────────────── #

# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)

# def normal_forms(raw: str) -> list[str]:
#     """
#     Return every lowercase key that could identify the player.

#     "Frankie (FD)" → ["frankie (fd)", "frankie", "fd"]
#     " FD "         → ["fd"]
#     """
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     keys = [raw.strip().lower()]
#     if before:
#         keys.append(before.strip().lower())
#     if inside:
#         keys.append(inside.strip().lower())
#     # drop duplicates while preserving order
#     return list(dict.fromkeys(keys))


# def parse_money(val) -> Decimal:
#     if pd.isna(val):
#         return Decimal("0")
#     return Decimal(str(val).replace("$", "").replace(",", "").strip())


# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"


# def load_payment_db(path: Path) -> Dict[str, List[str]]:
#     """
#     Build {lookup_key → ["(Venmo: @foo)", "(Cashapp: $bar)", …]}.

#     • For each player, generate keys: full name, name before '(', and nickname
#       inside '()' – all lowercase for case-insensitive matching.
#     • If the same key appears more than once, merge (union) the handle lists.
#     """
#     if not path.exists():
#         return {}

#     df = pd.read_csv(path)
#     db: Dict[str, List[str]] = {}

#     for _, row in df.iterrows():
#         raw_name = str(row["Player Name"]).strip()
#         handles: List[str] = []

#         # collect each non-blank handle
#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             label = col.strip()
#             if label.lower() == "venmo"   and not val.startswith("@"):
#                 val = "@" + val
#             if label.lower() == "cashapp" and not val.startswith("$"):
#                 val = "$" + val
#             handles.append(f"{label}: {val}")

#         # attach handles to every key variant
#         for key in normal_forms(raw_name):
#             if key not in db:
#                 db[key] = handles.copy()
#             else:
#                 seen = set(db[key])
#                 db[key].extend([h for h in handles if h not in seen])

#     return db


# def method_string(receiver_display: str, amt: Decimal, db: dict) -> str:
#     """
#     Compose the “Method” column string for *receiver_display* (case-insensitive).

#     Falls back to "(Venmo: )" if nothing is on file.
#     """
#     if receiver_display == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"

#     handles: List[str] = []
#     for key in normal_forms(receiver_display):
#         if key in db:
#             handles = db[key]
#             break

#     if not handles:
#         handles = ["Venmo: "]

#     joined = ", ".join(f"({h})" for h in handles)
#     return f"Pay user ${money_str(amt)} on {joined}"

# # ───────────────────────── ledger classification ────────────────────────── #

# def classify(df: pd.DataFrame) -> Tuple[
#         List[Tuple[str, Decimal]],   # creditors
#         List[Tuple[str, Decimal]],   # debtors
#         Decimal]:                    # cash collected by BANK
#     creditors, debtors = [], []
#     bank_balance = Decimal("0")

#     for idx, row in df.iterrows():
#         display = str(row["Player Name"]).strip()
#         node_id = f"{display} @row{idx}"      # ensures rebuy ≠ original
#         credit_flag = str(row["Credit?"]).strip().lower()
#         received   = parse_money(row.get("$ Received", 0))
#         ending     = parse_money(row.get("Ending Stack", 0))
#         pl_player  = parse_money(row.get("P/L Player", 0))
#         send_out   = parse_money(row.get("Send Out", 0))
#         sent_col   = parse_money(row.get("$ Sent", 0))

#         if credit_flag != "yes":              # NOT ledgered
#             bank_balance += received
#             if ending > 0:                    # cashed chips → bank owes them
#                 creditors.append((node_id, sent_col))
#         else:                                 # LEDGERED
#             if pl_player < 0:
#                 debtors  .append((node_id, abs(send_out)))
#             elif pl_player > 0:
#                 creditors.append((node_id, sent_col))

#     return creditors, debtors, bank_balance

# # ───────────────────── greedy settlement (cap = 3) ──────────────────────── #

# Transfer = Tuple[str, str, Decimal]          # (from, to, amount)

# def settle(creditors_in, debtors_in, max_out=3) -> List[Transfer]:
#     creditors = deque(sorted(
#         [(n, Decimal(a)) for n, a in creditors_in],
#         key=lambda x: x[1], reverse=True))
#     debtors   = sorted(
#         [(n, Decimal(a)) for n, a in debtors_in],
#         key=lambda x: x[1], reverse=True)

#     transfers: List[Transfer] = []
#     outcount  = defaultdict(int)             # outgoing edge count per node

#     for debtor, owe in debtors:
#         while owe > 0:
#             slots = max_out - outcount[debtor]
#             if slots == 0 or not creditors or creditors[0][1] == 0:
#                 transfers.append((debtor, "BANK", owe))
#                 outcount[debtor] += 1
#                 break

#             cred, need = creditors[0]

#             # last slot decision
#             if slots == 1:
#                 if need >= owe:
#                     pay = owe
#                     transfers.append((debtor, cred, pay))
#                     outcount[debtor] += 1
#                     need -= pay
#                     if need == 0:
#                         creditors.popleft()
#                 else:                         # owe > need → dump to BANK
#                     transfers.append((debtor, "BANK", owe))
#                     outcount[debtor] += 1
#                 break

#             # normal slot (slots ≥ 2)
#             pay = min(owe, need)
#             transfers.append((debtor, cred, pay))
#             outcount[debtor] += 1
#             owe  -= pay
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

# # ───────────────────────── 3-cycle cancellation ─────────────────────────── #

# def cancel_cycles(transfers: List[Transfer]) -> List[Transfer]:
#     graph = defaultdict(Decimal)
#     for fr, to, amt in transfers:
#         if fr == to or amt == 0:
#             continue
#         graph[(fr, to)] += amt

#     changed, loops = True, 0
#     while changed and loops < 100:
#         changed, loops = False, loops + 1
#         edges = list(graph.keys())
#         for (a, b) in edges:
#             if a == "BANK" or b == "BANK":
#                 continue
#             for (b2, c) in edges:
#                 if b2 != b or c == "BANK":
#                     continue
#                 if (c, a) in graph:
#                     x = min(graph[(a, b)], graph[(b, c)], graph[(c, a)])
#                     if x > 0:
#                         for e in [(a, b), (b, c), (c, a)]:
#                             graph[e] -= x
#                             if graph[e] == 0:
#                                 del graph[e]
#                         changed = True
#                         break
#             if changed:
#                 break
#     return [(fr, to, amt) for (fr, to), amt in graph.items()]

# # ─────────────────────────────── driver ─────────────────────────────────── #

# def main() -> None:
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--csv", required=True, help="Ledger CSV (Ledger Data/…)")

#     args = ap.parse_args()
#     ledger_path = Path(args.csv).expanduser()
#     if not ledger_path.exists():
#         raise SystemExit(f"Ledger file not found: {ledger_path}")

#     root_dir = Path(__file__).resolve().parents[1]
#     pay_db   = load_payment_db(root_dir / "Payment Type" / "Payment Methods.csv")
#     out_dir  = root_dir / "Transactions"
#     out_dir.mkdir(exist_ok=True)

#     # ---------- load & classify ----------
#     df = pd.read_csv(ledger_path)
#     creditors, debtors, bank_bal = classify(df)

#     if bank_bal > 0:
#         debtors.append(("BANK", bank_bal))
#     elif bank_bal < 0:
#         creditors.append(("BANK", -bank_bal))

#     # ---------- settle & prune ----------
#     transfers = settle(creditors, debtors, max_out=3)
#     transfers = cancel_cycles(transfers)

#     # merge duplicates
#     merged = defaultdict(Decimal)
#     for fr, to, amt in transfers:
#         merged[(fr, to)] += amt
#     transfers = sorted([(fr, to, amt) for (fr, to), amt in merged.items()],
#                        key=lambda x: (x[0], x[1]))

#     # ---------- write CSV ----------
#     date_tag = re.search(r"(\d{1,2}_\d{1,2}_\d{2})", ledger_path.stem)
#     tag = date_tag.group(1) if date_tag else "output"
#     out_path = out_dir / f"{tag}_transactions_v5.csv"

#     with out_path.open("w", newline="") as f:
#         wr = csv.writer(f)
#         wr.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in transfers:
#             fr_disp = fr.split(" @row")[0]
#             to_disp = to.split(" @row")[0]
#             wr.writerow([
#                 fr_disp,
#                 to_disp,
#                 money_str(amt),
#                 method_string(to_disp, amt, pay_db)
#             ])

#     print(f"✅  Wrote {out_path.relative_to(root_dir)} "
#           f"({len(transfers)} transfers, cap ≤3 achieved)")

# if __name__ == "__main__":
#     main()












########## THIS VERSION TRIES TO MATCH PAYMENT TO PAYMENT. DOES NOT WORK #####################




# #!/usr/bin/env python3
# """
# Backend/payoutSystem_v8.py
# ──────────────────────────
# • Matches debtor→creditor only when they share at least one payment app.
# • Soft cap 3, hard cap 4 outgoing transfers per ledger row.
# • Bank node supports all apps; overflow dumps go there.
# """

# from __future__ import annotations

# import argparse, csv, re
# from pathlib import Path
# from collections import defaultdict, deque
# from decimal import Decimal, getcontext
# from typing import Dict, List, Tuple, Set
# from dataclasses import dataclass          # ← moved up here

# import pandas as pd

# getcontext().prec = 28
# CENT = Decimal("0.01")

# ###############################################################################
# #                           ---- helper utils ----                            #
# ###############################################################################

# NAME_RE = re.compile(r"^\s*([^(]+?)(?:\s*\(([^)]+)\))?\s*$", re.A)
# ALL_APPS = {"venmo", "cashapp", "zelle", "applepay", "paypal"}

# def normal_forms(raw: str) -> list[str]:
#     m = NAME_RE.match(raw)
#     if not m:
#         return [raw.strip().lower()]
#     before, inside = m.group(1), m.group(2)
#     keys = [raw.strip().lower()]
#     if before:
#         keys.append(before.strip().lower())
#     if inside:
#         keys.append(inside.strip().lower())
#     return list(dict.fromkeys(keys))

# def parse_money(val) -> Decimal:
#     if pd.isna(val):
#         return Decimal("0")
#     return Decimal(str(val).replace("$", "").replace(",", "").strip())

# def money_str(x: Decimal) -> str:
#     return f"{x.quantize(CENT)}"

# @dataclass
# class PayInfo:
#     handles: List[str]
#     apps: Set[str]

# def load_payment_db(path: Path) -> Dict[str, PayInfo]:
#     if not path.exists():
#         return {}

#     df = pd.read_csv(path)
#     db: Dict[str, PayInfo] = {}

#     for _, row in df.iterrows():
#         raw_name = str(row["Player Name"]).strip()
#         handles, apps = [], set()

#         for col, val in row.items():
#             if col == "Player Name":
#                 continue
#             val = str(val).strip()
#             if not val or val.lower() == "nan":
#                 continue
#             label, app = col.strip(), col.strip().lower()
#             apps.add(app)
#             if app == "venmo" and not val.startswith("@"):
#                 val = "@" + val
#             if app == "cashapp" and not val.startswith("$"):
#                 val = "$" + val
#             handles.append(f"{label}: {val}")

#         info = PayInfo(handles, apps)

#         for key in normal_forms(raw_name):
#             if key not in db:
#                 db[key] = PayInfo(handles.copy(), apps.copy())
#             else:
#                 old = db[key]
#                 old.apps.update(apps)
#                 for h in handles:
#                     if h not in old.handles:
#                         old.handles.append(h)
#     return db

# def lookup_payinfo(name: str, db: Dict[str, PayInfo]) -> PayInfo:
#     for key in normal_forms(name):
#         if key in db:
#             return db[key]
#     return PayInfo(["Venmo: "], {"venmo"})

# def method_string(receiver: str, amt: Decimal, db: Dict[str, PayInfo]) -> str:
#     if receiver == "BANK":
#         return f"Internal bank transfer of ${money_str(amt)}"
#     handles = lookup_payinfo(receiver, db).handles
#     return f"Pay user ${money_str(amt)} on " + ", ".join(f"({h})" for h in handles)

# ###############################################################################
# #                       ---- ledger classification ----                       #
# ###############################################################################

# def classify(df: pd.DataFrame, pay_db: Dict[str, PayInfo]):
#     creditors, debtors, bank_bal = [], [], Decimal("0")
#     for idx, row in df.iterrows():
#         disp = str(row["Player Name"]).strip()
#         node = f"{disp} @row{idx}"
#         credit = str(row["Credit?"]).strip().lower()
#         recv   = parse_money(row.get("$ Received", 0))
#         ending = parse_money(row.get("Ending Stack", 0))
#         pl     = parse_money(row.get("P/L Player", 0))
#         send_o = parse_money(row.get("Send Out", 0))
#         sent   = parse_money(row.get("$ Sent", 0))

#         apps = lookup_payinfo(disp, pay_db).apps

#         if credit != "yes":            # not ledgered
#             bank_bal += recv
#             if ending > 0:
#                 creditors.append((node, sent, apps))
#         else:                          # ledgered
#             if pl < 0:
#                 debtors.append((node, abs(send_o), apps))
#             elif pl > 0:
#                 creditors.append((node, sent, apps))
#     return creditors, debtors, bank_bal

# ###############################################################################
# #                  ---- compatibility-aware settlement ----                   #
# ###############################################################################

# Transfer = Tuple[str, str, Decimal]

# def compat(a: Set[str], b: Set[str]) -> bool:
#     return bool(a & b)

# def settle(creditors_in, debtors_in, soft=3, hard=4) -> List[Transfer]:
#     cred = deque(sorted([(n, Decimal(a), ap) for n, a, ap in creditors_in],
#                         key=lambda x: x[1], reverse=True))
#     debt = sorted([(n, Decimal(a), ap) for n, a, ap in debtors_in],
#                   key=lambda x: x[1], reverse=True)

#     transfers, outcnt = [], defaultdict(int)

#     while debt:
#         d, owe, dapps = debt.pop(0)
#         while owe > 0:
#             if outcnt[d] >= hard:
#                 raise RuntimeError(f"{d} over hard cap")
#             if outcnt[d] >= soft:
#                 transfers.append((d, "BANK", owe))
#                 outcnt[d] += 1
#                 break

#             idx = next((i for i, (_, need, capps) in enumerate(cred)
#                         if need > 0 and compat(dapps, capps)), None)
#             if idx is None:
#                 transfers.append((d, "BANK", owe))
#                 outcnt[d] += 1
#                 break

#             cname, need, capps = cred[idx]
#             del cred[idx]

#             pay = min(owe, need)
#             transfers.append((d, cname, pay))
#             outcnt[d] += 1
#             owe  -= pay
#             need -= pay
#             if need > 0:
#                 cred.insert(idx, (cname, need, capps))

#     for cname, need, _ in cred:
#         if need > 0:
#             transfers.append(("BANK", cname, need))
#     return transfers

# def cancel_cycles(ts: List[Transfer]) -> List[Transfer]:
#     graph = defaultdict(Decimal)
#     for fr, to, amt in ts:
#         if fr != to and amt:
#             graph[(fr, to)] += amt

#     changed, loop = True, 0
#     while changed and loop < 100:
#         changed, loop = False, loop + 1
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

# ###############################################################################
# #                                   main                                     #
# ###############################################################################

# def main() -> None:
#     p = argparse.ArgumentParser()
#     p.add_argument("--csv", required=True)
#     p.add_argument("--soft", type=int, default=3,
#                    help="soft cap (default 3)")
#     p.add_argument("--hard", type=int, default=4,
#                    help="hard cap (default 4)")
#     a = p.parse_args()

#     ledger = Path(a.csv).expanduser()
#     if not ledger.exists():
#         raise SystemExit("Ledger file not found")

#     root = Path(__file__).resolve().parents[1]
#     paydb = load_payment_db(root / "Payment Type" / "Payment Methods.csv")
#     outdir = root / "Transactions"; outdir.mkdir(exist_ok=True)

#     df = pd.read_csv(ledger)
#     creds, debts, bank = classify(df, paydb)

#     if bank > 0:
#         debts.append(("BANK", bank, ALL_APPS.copy()))
#     elif bank < 0:
#         creds.append(("BANK", -bank, ALL_APPS.copy()))

#     transfers = settle(creds, debts, soft=a.soft, hard=a.hard)
#     transfers = cancel_cycles(transfers)

#     merged = defaultdict(Decimal)
#     for fr, to, amt in transfers:
#         merged[(fr, to)] += amt
#     transfers = sorted([(fr, to, amt) for (fr, to), amt in merged.items()], key=lambda x: (x[0], x[1]))

#     m = re.search(r"(\d{1,2}_\d{1,2}_\d{2})", ledger.stem)
#     tag = m.group(1) if m else "output"
#     outpath = outdir / f"{tag}_transactions_v8.csv"

#     with outpath.open("w", newline="") as f:
#         w = csv.writer(f)
#         w.writerow(["From", "To", "Amount", "Method"])
#         for fr, to, amt in transfers:
#             fr_disp, to_disp = fr.split(" @row")[0], to.split(" @row")[0]
#             w.writerow([fr_disp, to_disp, money_str(amt),
#                         method_string(to_disp, amt, paydb)])

#     print(f"✅  Wrote {outpath.relative_to(root)} "
#           f"({len(transfers)} transfers; soft {a.soft}, hard {a.hard})")

# if __name__ == "__main__":
#     main()
