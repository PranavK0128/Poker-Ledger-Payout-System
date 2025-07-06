# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, identifies who owes money and who is owed,
# then produces the minimal set of peer-to-peer transactions to settle
# everyone in as few transfers as possible.  Any leftover credit
# (i.e. winners who still haven’t gotten their full payout) is
# shown as BANK → player.  Any leftover debt (unlikely) shows
# player → BANK.

# This version prioritizes minimizing transactions involving the bank,
# then, as a secondary goal, minimizes total transactions among all players.
# """

# import argparse
# import os
# import itertools
# import pandas as pd


# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0


# def settle_transactions(csv_path, bank_name="BANK"):
#     df = pd.read_csv(csv_path)

#     # Build initial debtors & creditors lists
#     base_debtors, base_creditors = [], []
#     for _, row in df.iterrows():
#         name       = row['Player Name']
#         credit_yes = str(row['Credit?']).strip().lower() == 'yes'
#         end_stack  = parse_currency(row['Ending Stack'])
#         pl         = parse_currency(row['P/L Player'])
#         send_out   = parse_currency(row['Send Out'])
#         sent       = parse_currency(row['$ Sent'])

#         if not credit_yes:
#             # Non-ledgered losses have end_stack == 0 by spec; profits use post-tip $ Sent
#             if end_stack > 0 and sent > 0:
#                 base_creditors.append([name, sent])
#         else:
#             if pl < 0 and abs(send_out) > 0:
#                 # ledgered loss → owes us
#                 base_debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 # ledgered profit → use post-tip $ Sent
#                 base_creditors.append([name, sent])

#     # Simulation helper: perform greedy matching under given sort orders
#     def simulate(debt_rev, cred_rev):
#         # Copy lists
#         debtors   = [d.copy() for d in base_debtors]
#         creditors = [c.copy() for c in base_creditors]
#         # Sort according to flags
#         debtors.sort(key=lambda x: x[1], reverse=debt_rev)
#         creditors.sort(key=lambda x: x[1], reverse=cred_rev)

#         matches = []
#         i, j = 0, 0
#         # Greedy peer-to-peer matching
#         while i < len(debtors) and j < len(creditors):
#             d_name, d_amt = debtors[i]
#             c_name, c_amt = creditors[j]
#             x = min(d_amt, c_amt)
#             matches.append({'From': d_name, 'To': c_name, 'Amount': round(x, 2)})
#             debtors[i][1]   -= x
#             creditors[j][1] -= x
#             if abs(debtors[i][1]) < 1e-6:
#                 i += 1
#             if abs(creditors[j][1]) < 1e-6:
#                 j += 1

#         # Count leftover participants → bank transactions
#         leftover_bank = sum(1 for k in range(j, len(creditors)) if creditors[k][1] > 1e-6)
#         leftover_bank += sum(1 for k in range(i, len(debtors)) if debtors[k][1]   > 1e-6)
#         total_txns    = len(matches) + leftover_bank
#         return leftover_bank, total_txns, matches, debtors, creditors, i, j

#     # Evaluate all 4 sort-order strategies
#     strategies = [(dr, cr) for dr in (True, False) for cr in (True, False)]
#     best = None
#     for dr, cr in strategies:
#         lb, tt, m, d_list, c_list, di, cj = simulate(dr, cr)
#         metrics = (lb, tt)
#         if best is None or metrics < best[0]:
#             best = (metrics, dr, cr, m, d_list, c_list, di, cj)

#     # Unpack the best strategy
#     (_, _), debt_rev, cred_rev, matches, debtors, creditors, idx_debt, idx_cred = best

#     # Build final transactions: peer-to-peer first
#     transactions = list(matches)
#     # Any creditors left → bank pays them
#     for k in range(idx_cred, len(creditors)):
#         name, amt = creditors[k]
#         if amt > 1e-6:
#             transactions.append({'From': bank_name, 'To': name, 'Amount': round(amt, 2)})
#     # Any debtors left → they pay bank
#     for k in range(idx_debt, len(debtors)):
#         name, amt = debtors[k]
#         if amt > 1e-6:
#             transactions.append({'From': name, 'To': bank_name, 'Amount': round(amt, 2)})

#     # Write CSV
#     trans_df    = pd.DataFrame(transactions)
#     abs_csv     = os.path.abspath(csv_path)
#     ledger_dir  = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)
#     out_dir     = os.path.join(project_root, 'Transactions')
#     os.makedirs(out_dir, exist_ok=True)

#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactions.csv")
#     trans_df.to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(transactions)} transactions "
#           f"(bank-limited strategy dr={debt_rev}, cr={cred_rev}) to:\n    {out_path}")


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — settle all debts with minimal transfers"
#     )
#     p.add_argument(
#         '--csv', required=True,
#         help="Path to your ledger CSV (e.g. \"Ledger Data/6_25_25.csv\")"
#     )
#     p.add_argument(
#         '--bank-name', default="BANK",
#         help="Name to use for the host/bank in any top-off transactions"
#     )
#     args = p.parse_args()
#     settle_transactions(args.csv, bank_name=args.bank_name)


# if __name__ == "__main__":
#     main()















# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, identifies who owes money and who is owed,
# then produces peer-to-peer transactions >= $1, and rolls any smaller 
# amounts back to the BANK, so no player is ever asked to send under $1.
# The BANK’s own settlements will include exact pennies to close out.
# """

# import argparse
# import os
# import itertools
# import pandas as pd


# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0


# def settle_transactions(csv_path, bank_name="BANK", min_peer_txn=1.0):
#     df = pd.read_csv(csv_path)

#     # 1) Build raw debtor & creditor pools (same as before)
#     base_debtors, base_creditors = [], []
#     for _, row in df.iterrows():
#         name       = row['Player Name']
#         credit_yes = str(row['Credit?']).strip().lower() == 'yes'
#         end_stack  = parse_currency(row['Ending Stack'])
#         pl         = parse_currency(row['P/L Player'])
#         send_out   = parse_currency(row['Send Out'])
#         sent       = parse_currency(row['$ Sent'])

#         if not credit_yes and end_stack > 0 and sent > 0:
#             base_creditors.append([name, sent])
#         elif credit_yes:
#             if pl < 0 and abs(send_out) > 0:
#                 base_debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 base_creditors.append([name, sent])

#     # 2) Greedy match helper
#     def simulate(dr, cr):
#         debtors   = [d.copy() for d in base_debtors]
#         creditors = [c.copy() for c in base_creditors]
#         debtors.sort(key=lambda x: x[1], reverse=dr)
#         creditors.sort(key=lambda x: x[1], reverse=cr)

#         matches = []
#         i = j = 0
#         while i < len(debtors) and j < len(creditors):
#             dn, da = debtors[i]
#             cn, ca = creditors[j]
#             x = min(da, ca)
#             matches.append({'From': dn, 'To': cn, 'Amount': round(x, 2)})
#             debtors[i][1]   -= x
#             creditors[j][1] -= x
#             if debtors[i][1]   < 1e-6: i += 1
#             if creditors[j][1] < 1e-6: j += 1

#         # count bank txns if we rolled everything sub-$1
#         leftover_bank = sum(1 for k in range(i, len(debtors))   if debtors[k][1]   > 1e-6)
#         leftover_bank += sum(1 for k in range(j, len(creditors)) if creditors[k][1] > 1e-6)
#         total_txns = len(matches) + leftover_bank
#         return leftover_bank, total_txns, matches, debtors, creditors, i, j

#     # 3) Pick best sort order (bank‐first, then total)
#     best = None
#     for dr, cr in itertools.product([True, False], repeat=2):
#         lb, tt, m, dl, cl, di, cj = simulate(dr, cr)
#         if best is None or (lb, tt) < best[0]:
#             best = ((lb, tt), dr, cr, m, dl, cl, di, cj)

#     (_, _), debt_rev, cred_rev, matches, debtors, creditors, idx_d, idx_c = best

#     # 4) **Split up any < $1 peer matches** by borrowing cents from a larger peer match
#     to_bank = []  # will hold matches we can’t rescue
#     # group match indices by debtor
#     from collections import defaultdict
#     debtor_matches = defaultdict(list)
#     for i,tx in enumerate(matches):
#         debtor_matches[tx['From']].append(i)

#     for debtor, idxs in debtor_matches.items():
#         # keep looping until no < $1 left or no donors
#         for idx in list(idxs):
#             amt = matches[idx]['Amount']
#             if amt < min_peer_txn:
#                 need = min_peer_txn - amt
#                 # find a donor index with >= need + min_peer_txn
#                 donor = next(
#                     (j for j in idxs
#                      if j != idx and matches[j]['Amount'] >= min_peer_txn + need),
#                     None
#                 )
#                 if donor is not None:
#                     # borrow 'need' cents
#                     matches[donor]['Amount'] = round(matches[donor]['Amount'] - need, 2)
#                     matches[idx]['Amount']   = round(matches[idx]['Amount'] + need, 2)
#                 else:
#                     # can’t rescue this small match → send to bank
#                     to_bank.append(matches[idx])
#                     matches[idx]['Amount'] = 0.0  # drop from peer list

#     # collect the surviving peer-to-peer transactions
#     peer_txns = [tx for tx in matches
#                  if tx['Amount'] >= min_peer_txn]

#     # 5) **Return any totally dropped small matches** back to the pools
#     for tx in to_bank:
#         amt = tx['Amount'] or 0.0
#         # restore to debtor
#         for d in debtors:
#             if d[0] == tx['From']:
#                 d[1] += amt
#                 break
#         # restore to creditor
#         for c in creditors:
#             if c[0] == tx['To']:
#                 c[1] += amt
#                 break

#     # 6) Build final: peer-to-peer ≥ $1, then bank settles **all** leftovers exactly
#     final_txns = peer_txns[:]
#     # bank → creditors
#     for name, amt in creditors[idx_c:]:
#         if amt > 1e-6:
#             final_txns.append({'From': bank_name, 'To': name, 'Amount': round(amt, 2)})
#     # debtors → bank
#     for name, amt in debtors[idx_d:]:
#         if amt > 1e-6:
#             final_txns.append({'From': name, 'To': bank_name, 'Amount': round(amt, 2)})

#     # 7) Write CSV (same as before)
#     trans_df     = pd.DataFrame(final_txns)
#     abs_csv      = os.path.abspath(csv_path)
#     ledger_dir   = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)
#     out_dir      = os.path.join(project_root, 'Transactions')
#     os.makedirs(out_dir, exist_ok=True)

#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactions.csv")
#     trans_df.to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(final_txns)} transactions "
#           f"(bank‐limited strategy dr={debt_rev}, cr={cred_rev}) to:\n    {out_path}")


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — peer-to-peer >= $1, BANK handles pennies"
#     )
#     p.add_argument('--csv',      required=True,
#                    help='Path to your ledger CSV (e.g. "Ledger Data/6_25_25.csv")')
#     p.add_argument('--bank-name', default="BANK",
#                    help='Label for host/bank on any settlements')
#     p.add_argument('--min-peer', type=float, default=1.0,
#                    help='Minimum peer-to-peer txn amount ($1 by default)')
#     args = p.parse_args()

#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name,
#         min_peer_txn=args.min_peer
#     )


# if __name__ == "__main__":
#     main()















# #!/usr/bin/env python3
# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, validates every player against
# Payment Type(s)/Payment Methods.csv, then produces peer-to-peer
# transactions ≥ $1 (borrowing cents where possible), rolling any
# true “dust” under $1 back to the BANK for its final settlements.
# """

# import argparse
# import os
# import sys
# import itertools
# from collections import defaultdict
# import pandas as pd


# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0


# def settle_transactions(csv_path, bank_name="BANK", min_peer_txn=1.0):
#     # 1) Load ledger CSV
#     df = pd.read_csv(csv_path)

#     # 2) Payment-Methods validation
#     abs_csv      = os.path.abspath(csv_path)
#     ledger_dir   = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)

#     pm_path = None
#     for dname in ("Payment Types", "Payment Type"):
#         candidate = os.path.join(project_root, dname, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break

#     if pm_path is None:
#         print("✗ Error: cannot find Payment Methods.csv. Looked in:")
#         print(f"  • {os.path.join(project_root, 'Payment Types', 'Payment Methods.csv')}")
#         print(f"  • {os.path.join(project_root, 'Payment Type',  'Payment Methods.csv')}")
#         sys.exit(1)

#     pm_df      = pd.read_csv(pm_path)
#     pm_entries = pm_df["Player Name"].astype(str).tolist()

#     # Build set of valid discord‐names: the text inside () if present, else the whole entry
#     valid_discord = set()
#     for e in pm_entries:
#         e = e.strip()
#         lower = e.lower()
#         if "(" in e and ")" in e:
#             inside = e.split("(", 1)[1].split(")", 1)[0].strip().lower()
#             valid_discord.add(inside)
#         else:
#             valid_discord.add(lower)

#     # Now check each ledger Player Name
#     missing = []
#     for full in df["Player Name"].unique():
#         if pd.isnull(full):
#             continue
#         full_str = str(full).strip()
#         if full_str == "":
#             continue
#         # ledger names are "DiscordName" or "DiscordName (PokerNowName)"
#         discord = full_str.split("(", 1)[0].strip().lower()
#         if discord not in valid_discord:
#             missing.append(full_str)

#     if missing:
#         print("✗ Error: no payment methods found for these ledger players:")
#         for name in missing:
#             print(f"  • {name}")
#         sys.exit(1)

#     # 3) Build raw debtor & creditor pools
#     base_debtors   = []
#     base_creditors = []
#     for _, row in df.iterrows():
#         name       = row["Player Name"]
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         pl         = parse_currency(row["P/L Player"])
#         send_out   = parse_currency(row["Send Out"])
#         sent       = parse_currency(row["$ Sent"])

#         if not credit_yes and end_stack > 0 and sent > 0:
#             base_creditors.append([name, sent])
#         elif credit_yes:
#             if pl < 0 and abs(send_out) > 0:
#                 base_debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 base_creditors.append([name, sent])

#     # 4) Greedy matching helper
#     def simulate(dr, cr):
#         debtors   = [d.copy() for d in base_debtors]
#         creditors = [c.copy() for c in base_creditors]
#         debtors.sort(key=lambda x: x[1], reverse=dr)
#         creditors.sort(key=lambda x: x[1], reverse=cr)

#         matches = []
#         i = j = 0
#         while i < len(debtors) and j < len(creditors):
#             dn, da = debtors[i]
#             cn, ca = creditors[j]
#             x = min(da, ca)
#             matches.append({"From": dn, "To": cn, "Amount": round(x, 2)})
#             debtors[i][1]   -= x
#             creditors[j][1] -= x
#             if debtors[i][1]   < 1e-6: i += 1
#             if creditors[j][1] < 1e-6: j += 1

#         leftover_bank = sum(1 for k in range(i, len(debtors))   if debtors[k][1]   > 1e-6)
#         leftover_bank += sum(1 for k in range(j, len(creditors)) if creditors[k][1] > 1e-6)
#         total_txns = len(matches) + leftover_bank
#         return leftover_bank, total_txns, matches, debtors, creditors, i, j

#     # 5) Pick best sort order (minimize bank → then total txns)
#     best = None
#     for dr, cr in itertools.product([True, False], repeat=2):
#         lb, tt, m, dl, cl, di, cj = simulate(dr, cr)
#         if best is None or (lb, tt) < best[0]:
#             best = ((lb, tt), dr, cr, m, dl, cl, di, cj)

#     (_, _), debt_rev, cred_rev, matches, debtors, creditors, idx_d, idx_c = best

#     # 6) Split up any < $1 peer matches by borrowing cents
#     to_bank = []
#     debtor_matches = defaultdict(list)
#     for i, tx in enumerate(matches):
#         debtor_matches[tx["From"]].append(i)

#     for debtor, idxs in debtor_matches.items():
#         for idx in list(idxs):
#             amt = matches[idx]["Amount"]
#             if amt < min_peer_txn:
#                 need = min_peer_txn - amt
#                 donor = next(
#                     j for j in idxs
#                     if j != idx and matches[j]["Amount"] >= min_peer_txn + need
#                 ) if idxs else None
#                 if donor is not None:
#                     matches[donor]["Amount"] = round(matches[donor]["Amount"] - need, 2)
#                     matches[idx]["Amount"]   = round(matches[idx]["Amount"] + need, 2)
#                 else:
#                     to_bank.append(matches[idx])
#                     matches[idx]["Amount"] = 0.0

#     peer_txns = [tx for tx in matches if tx["Amount"] >= min_peer_txn]

#     # 7) Return any dropped small matches into pools
#     for tx in to_bank:
#         amt = tx["Amount"] or 0.0
#         for d in debtors:
#             if d[0] == tx["From"]:
#                 d[1] += amt
#                 break
#         for c in creditors:
#             if c[0] == tx["To"]:
#                 c[1] += amt
#                 break

#     # 8) Finalize: peer-to-peer ≥ $1, then bank settles all exact pennies
#     final_txns = peer_txns[:]
#     for name, amt in creditors[idx_c:]:
#         if amt > 1e-6:
#             final_txns.append({"From": bank_name, "To": name, "Amount": round(amt, 2)})
#     for name, amt in debtors[idx_d:]:
#         if amt > 1e-6:
#             final_txns.append({"From": name, "To": bank_name, "Amount": round(amt, 2)})

#     # 9) Write out CSV
#     trans_df = pd.DataFrame(final_txns)
#     out_dir  = os.path.join(project_root, "Transactions")
#     os.makedirs(out_dir, exist_ok=True)
#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactions.csv")
#     trans_df.to_csv(out_path, index=False)

#     print(
#         f"[✓] Wrote {len(final_txns)} transactions "
#         f"(bank‐limited strategy dr={debt_rev}, cr={cred_rev}) to:\n    {out_path}"
#     )


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — peer-to-peer ≥ $1, BANK handles pennies"
#     )
#     p.add_argument(
#         "--csv", required=True,
#         help='Path to your ledger CSV (e.g. "Ledger Data/6_30_25.csv")'
#     )
#     p.add_argument(
#         "--bank-name", default="BANK",
#         help="Label for host/bank on any settlements"
#     )
#     p.add_argument(
#         "--min-peer", type=float, default=1.0,
#         help="Minimum peer-to-peer txn amount ($1 by default)"
#     )
#     args = p.parse_args()

#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name,
#         min_peer_txn=args.min_peer
#     )


# if __name__ == "__main__":
#     main()









# v1.6 MAKES SOMEONE WITHOUT A SPECIFIC PAYMENT APP PAY ANOTHER PERSON WHO ONLY HAS THAT PAYMENT APP




# #!/usr/bin/env python3
# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, validates every player against
# Payment Type(s)/Payment Methods.csv (defaulting missing players to Venmo),
# then produces peer-to-peer transactions ≥ $1 (borrowing cents where possible),
# rolling any true “dust” under $1 back to the BANK for its final settlements,
# and appending each receiver’s payment handle.
# """

# import argparse
# import os
# import sys
# import itertools
# from collections import defaultdict
# import pandas as pd


# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0


# def settle_transactions(csv_path, bank_name="BANK", min_peer_txn=1.0):
#     # 1) Load ledger CSV
#     df = pd.read_csv(csv_path)

#     # 2) Load Payment Methods, build pm_map: discord → full row or None
#     abs_csv      = os.path.abspath(csv_path)
#     ledger_dir   = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)

#     pm_path = None
#     for dname in ("Payment Types", "Payment Type"):
#         candidate = os.path.join(project_root, dname, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break

#     if pm_path is None:
#         print("✗ Error: cannot find Payment Methods.csv. Looked in:")
#         print(f"  • {os.path.join(project_root, 'Payment Types', 'Payment Methods.csv')}")
#         print(f"  • {os.path.join(project_root, 'Payment Type',  'Payment Methods.csv')}")
#         sys.exit(1)

#     pm_df = pd.read_csv(pm_path)
#     pm_map = {}
#     for _, row in pm_df.iterrows():
#         entry = str(row["Player Name"]).strip()
#         lower = entry.lower()
#         if "(" in entry and ")" in entry:
#             before = entry.split("(", 1)[0].strip().lower()
#             inside = entry.split("(", 1)[1].split(")", 1)[0].strip().lower()
#             pm_map[before] = row
#             pm_map[inside] = row
#         else:
#             pm_map[lower] = row

#     # 3) Warn about missing players but default them to Venmo
#     missing = []
#     for full in df["Player Name"].unique():
#         if pd.isnull(full): continue
#         full_str = str(full).strip()
#         if not full_str: continue
#         discord = full_str.split("(", 1)[0].strip().lower()
#         if discord not in pm_map:
#             missing.append(discord)
#             pm_map[discord] = None

#     if missing:
#         print("⚠ Warning: no payment methods found for these players; defaulting them to Venmo:")
#         for name in missing:
#             print(f"  • {name}")

#     # 4) Build raw debtor & creditor pools
#     base_debtors   = []
#     base_creditors = []
#     for _, row in df.iterrows():
#         name       = row["Player Name"]
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         pl         = parse_currency(row["P/L Player"])
#         send_out   = parse_currency(row["Send Out"])
#         sent       = parse_currency(row["$ Sent"])

#         if not credit_yes and end_stack > 0 and sent > 0:
#             base_creditors.append([name, sent])
#         elif credit_yes:
#             if pl < 0 and abs(send_out) > 0:
#                 base_debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 base_creditors.append([name, sent])

#     # 5) Greedy-match helper
#     def simulate(dr, cr):
#         debtors   = [d.copy() for d in base_debtors]
#         creditors = [c.copy() for c in base_creditors]
#         debtors.sort(key=lambda x: x[1], reverse=dr)
#         creditors.sort(key=lambda x: x[1], reverse=cr)

#         matches = []
#         i = j = 0
#         while i < len(debtors) and j < len(creditors):
#             dn, da = debtors[i]
#             cn, ca = creditors[j]
#             x = min(da, ca)
#             matches.append({"From": dn, "To": cn, "Amount": round(x, 2)})
#             debtors[i][1]   -= x
#             creditors[j][1] -= x
#             if debtors[i][1]   < 1e-6: i += 1
#             if creditors[j][1] < 1e-6: j += 1

#         leftover_bank = sum(1 for k in range(i, len(debtors))   if debtors[k][1]   > 1e-6)
#         leftover_bank += sum(1 for k in range(j, len(creditors)) if creditors[k][1] > 1e-6)
#         return leftover_bank, len(matches) + leftover_bank, matches, debtors, creditors, i, j

#     # 6) Pick best sort-order strategy
#     best = None
#     for dr, cr in itertools.product([True, False], repeat=2):
#         lb, tt, m, dl, cl, di, cj = simulate(dr, cr)
#         if best is None or (lb, tt) < best[0]:
#             best = ((lb, tt), dr, cr, m, dl, cl, di, cj)

#     (_, _), debt_rev, cred_rev, matches, debtors, creditors, idx_d, idx_c = best

#     # 7) Split any < $1 peer matches by borrowing cents
#     to_bank = []
#     debtor_matches = defaultdict(list)
#     for i, tx in enumerate(matches):
#         debtor_matches[tx["From"]].append(i)

#     for debtor, idxs in debtor_matches.items():
#         for idx in list(idxs):
#             amt = matches[idx]["Amount"]
#             if amt < min_peer_txn:
#                 need = min_peer_txn - amt
#                 donor = next(
#                     (j for j in idxs if j != idx and matches[j]["Amount"] >= min_peer_txn + need),
#                     None
#                 )
#                 if donor is not None:
#                     matches[donor]["Amount"] = round(matches[donor]["Amount"] - need, 2)
#                     matches[idx]["Amount"]   = round(matches[idx]["Amount"] + need, 2)
#                 else:
#                     to_bank.append(matches[idx])
#                     matches[idx]["Amount"] = 0.0

#     peer_txns = [tx for tx in matches if tx["Amount"] >= min_peer_txn]

#     # 8) Return any dropped small matches into pools
#     for tx in to_bank:
#         amt = tx["Amount"] or 0.0
#         for d in debtors:
#             if d[0] == tx["From"]:
#                 d[1] += amt
#                 break
#         for c in creditors:
#             if c[0] == tx["To"]:
#                 c[1] += amt
#                 break

#     # 9) Finalize: peer-to-peer ≥ $1, then bank settles all pennies
#     final_txns = list(peer_txns)
#     for name, amt in creditors[idx_c:]:
#         if amt > 1e-6:
#             final_txns.append({"From": bank_name, "To": name, "Amount": round(amt, 2)})
#     for name, amt in debtors[idx_d:]:
#         if amt > 1e-6:
#             final_txns.append({"From": name, "To": bank_name, "Amount": round(amt, 2)})

#     # 10) Attach receiver’s payment handle in "Method" column
#     for tx in final_txns:
#         to_name = str(tx["To"]).split("(", 1)[0].strip().lower()
#         row     = pm_map.get(to_name)
#         method  = "venmo"
#         if row is not None:
#             for col in ("Venmo", "Zelle", "Cashapp", "ApplePay"):
#                 val = row.get(col, "")
#                 if pd.notnull(val) and str(val).strip():
#                     method = str(val).strip()
#                     break
#         tx["Method"] = method

#     # 11) Write out CSV with Method
#     out_dir = os.path.join(project_root, "Transactions")
#     os.makedirs(out_dir, exist_ok=True)
#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactions.csv")
#     pd.DataFrame(final_txns).to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(final_txns)} transactions "
#           f"(bank-limited strategy dr={debt_rev}, cr={cred_rev}) to:\n    {out_path}")


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — outputs receiver’s payment handle"
#     )
#     p.add_argument("--csv",      required=True,
#                    help="Path to your ledger CSV (e.g. 'Ledger Data/6_30_25.csv')")
#     p.add_argument("--bank-name", default="BANK",
#                    help="Label for host/bank on any settlements")
#     p.add_argument("--min-peer",  type=float, default=1.0,
#                    help="Minimum peer-to-peer txn amount ($1 by default)")
#     args = p.parse_args()

#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name,
#         min_peer_txn=args.min_peer
#     )


# if __name__ == "__main__":
#     main()













#BANK TRANSACTIONS NOT SHOWN





# #!/usr/bin/env python3
# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, loads Payment Methods.csv (defaulting missing to Venmo),
# then settles everyone with peer-to-peer transfers ≥ $1 when they share an app,
# or routes along a multi-hop chain of players with shared apps to avoid BANK whenever possible.
# Appends “Method” as “Venmo: @handle”, etc.
# """

# import argparse, os, sys, itertools
# from collections import defaultdict, deque
# import pandas as pd

# def parse_currency(val):
#     if pd.isnull(val): return 0.0
#     if isinstance(val, (int, float)): return float(val)
#     s = str(val).replace('$','').replace(',','').strip()
#     try: return float(s)
#     except: return 0.0

# def settle_transactions(csv_path, bank_name="BANK", min_peer=1.0):
#     # 1) Load ledger
#     df = pd.read_csv(csv_path)

#     # 2) Load payment methods
#     root = os.path.dirname(os.path.dirname(os.path.abspath(csv_path)))
#     pm_file = None
#     for d in ("Payment Types","Payment Type"):
#         p = os.path.join(root, d, "Payment Methods.csv")
#         if os.path.isfile(p):
#             pm_file = p; break
#     if not pm_file:
#         print("✗ Missing Payment Methods.csv"); sys.exit(1)
#     pm_df = pd.read_csv(pm_file)
#     apps = ["Venmo","Zelle","Cashapp","ApplePay"]

#     # build discord->row map
#     pm_map = {}
#     for _,r in pm_df.iterrows():
#         name = str(r["Player Name"]).strip()
#         low = name.lower()
#         if "(" in name and ")" in name:
#             pre = name.split("(",1)[0].strip().lower()
#             ins = name.split("(",1)[1].split(")",1)[0].strip().lower()
#             pm_map[pre] = r; pm_map[ins] = r
#         else:
#             pm_map[low] = r
#     # default missing to None
#     for full in df["Player Name"].dropna().unique():
#         d0 = str(full).split("(",1)[0].strip().lower()
#         if d0 and d0 not in pm_map:
#             pm_map[d0] = None

#     # helper: apps available for discord (empty list if None)
#     def get_apps(discord):
#         row = pm_map.get(discord)
#         if row is None:
#             return []
#         return [app for app in apps
#                 if pd.notnull(row.get(app)) and str(row.get(app)).strip()]

#     # 3) Build debtors & creditors lists
#     debtors, creditors = [], []
#     for _,row in df.iterrows():
#         name = row["Player Name"]
#         cred_flag = str(row["Credit?"]).strip().lower()=="yes"
#         end_stack = parse_currency(row["Ending Stack"])
#         pl = parse_currency(row["P/L Player"])
#         so = parse_currency(row["Send Out"])
#         sent = parse_currency(row["$ Sent"])
#         if not cred_flag and end_stack>0 and sent>0:
#             creditors.append([name, sent])
#         elif cred_flag:
#             if pl<0 and so<0:
#                 debtors.append([name, abs(so)])
#             elif pl>0 and sent>0:
#                 creditors.append([name, sent])

#     # 4) Greedy match helper
#     def simulate(dr,cr):
#         ds = [d.copy() for d in debtors]
#         cs = [c.copy() for c in creditors]
#         ds.sort(key=lambda x:x[1], reverse=dr)
#         cs.sort(key=lambda x:x[1], reverse=cr)
#         matches,i,j = [],0,0
#         while i<len(ds) and j<len(cs):
#             dn,da = ds[i]; cn,ca = cs[j]
#             x = min(da,ca)
#             matches.append({"From":dn,"To":cn,"Amount":round(x,2)})
#             ds[i][1]-=x; cs[j][1]-=x
#             if ds[i][1]<1e-6: i+=1
#             if cs[j][1]<1e-6: j+=1
#         rb = sum(1 for k in range(i,len(ds)) if ds[k][1]>1e-6) \
#            + sum(1 for k in range(j,len(cs)) if cs[k][1]>1e-6)
#         return rb, len(matches)+rb, matches, ds, cs, i, j

#     # 5) Pick best sort order
#     best=None
#     for dr,cr in itertools.product([True,False],repeat=2):
#         rb,tt,ms,ds,cs,di,ci = simulate(dr,cr)
#         if best is None or (rb,tt)<best[0]:
#             best=((rb,tt),dr,cr,ms,ds,cs,di,ci)
#     (_, _),dr,cr,matches,debtors,creditors,idx_d,idx_c = best

#     # 6) Reallocate < $1 peer matches
#     to_bank=[]; dm=defaultdict(list)
#     for i,tx in enumerate(matches):
#         dm[tx["From"]].append(i)
#     for deb,idxs in dm.items():
#         for idx in list(idxs):
#             amt=matches[idx]["Amount"]
#             if amt<min_peer:
#                 need=min_peer-amt
#                 donor=next((j for j in idxs
#                             if j!=idx and matches[j]["Amount"]>=min_peer+need),
#                            None)
#                 if donor is not None:
#                     matches[donor]["Amount"]-=need
#                     matches[idx]["Amount"]+=need
#                 else:
#                     to_bank.append(matches[idx]); matches[idx]["Amount"]=0.0
#     peer = [tx for tx in matches if tx["Amount"]>=min_peer]
#     # return dust
#     for tx in to_bank:
#         amt=tx["Amount"] or 0.0
#         for d in debtors:
#             if d[0]==tx["From"]: d[1]+=amt; break
#         for c in creditors:
#             if c[0]==tx["To"]:   c[1]+=amt; break

#     # 7) Build adjacency graph among players (exclude bank)
#     players = {tx["From"].split("(",1)[0].strip().lower() for tx in peer} \
#             | {tx["To"].split("(",1)[0].strip().lower() for tx in peer}
#     graph = defaultdict(list)
#     for u in players:
#         for v in players:
#             if u==v: continue
#             if set(get_apps(u)) & set(get_apps(v)):
#                 graph[u].append(v)

#     # helper: find path from u→v avoiding bank
#     def find_path(u,v):
#         u0=u.split("(",1)[0].strip().lower()
#         v0=v.split("(",1)[0].strip().lower()
#         q=deque([[u0]])
#         seen={u0}
#         while q:
#             path=q.popleft()
#             last=path[-1]
#             if last==v0: return path
#             for nb in graph[last]:
#                 if nb not in seen:
#                     seen.add(nb)
#                     q.append(path+[nb])
#         return None

#     # 8) Route payments: prefer direct, else multi-hop
#     final=[]
#     for tx in peer:
#         amt=tx["Amount"]
#         frm=tx["From"]; to=tx["To"]
#         path=find_path(frm,to)
#         if path and len(path)>=2:
#             # break into segments
#             for i in range(len(path)-1):
#                 s=path[i]; r=path[i+1]
#                 # find original casing names
#                 s_name = frm if i==0 else next(p for p,_ in debtors+creditors if p.lower().startswith(s))
#                 r_name = to if i==len(path)-2 else next(p for p,_ in debtors+creditors if p.lower().startswith(r))
#                 # choose common app
#                 apps_s=get_apps(s); apps_r=get_apps(r)
#                 common= next((app for app in apps if app in apps_s and app in apps_r), "Venmo")
#                 handle = ""
#                 row_r = pm_map.get(r)
#                 if row_r is not None and pd.notnull(row_r.get(common)):
#                     handle=str(row_r.get(common)).strip()
#                 final.append({"From":s_name,"To":r_name,"Amount":amt,"Method":f"{common}: {handle}"})
#         else:
#             # no route => direct via Venmo fallback
#             final.append({"From":frm,"To":to,"Amount":amt,"Method":"Venmo:"})

#     # 9) Write out CSV
#     out = pd.DataFrame(final)
#     out_dir = os.path.join(root,"Transactions")
#     os.makedirs(out_dir,exist_ok=True)
#     fname = os.path.splitext(os.path.basename(csv_path))[0]+"_transactions.csv"
#     out.to_csv(os.path.join(out_dir,fname),index=False)
#     print(f"[✓] Wrote {len(final)} transactions → {fname}")

# def main():
#     p=argparse.ArgumentParser()
#     p.add_argument("--csv", required=True)
#     p.add_argument("--bank-name", default="BANK")
#     p.add_argument("--min-peer", type=float, default=1.0)
#     args=p.parse_args()
#     settle_transactions(args.csv, args.bank_name, args.min_peer)

# if __name__=="__main__":
#     main()










# BANK HAS TOO MANY TRANSACTIONS HERE





# #!/usr/bin/env python3
# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, loads Payment Methods.csv (defaulting missing to Venmo-only),
# then settles debts via:
#  1) direct peer-to-peer transfers ≥ $1 when sender and receiver share Venmo, Zelle, or ApplePay (skipping Cashapp),
#  2) finally, BANK steps in to pay any remaining creditors (including all Cashapp balances).
# Each transaction is annotated “App: handle” for the receiver’s handle on that app.
# """

# import argparse
# import os
# import pandas as pd


# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     try:
#         return float(val)
#     except:
#         s = str(val).replace('$', '').replace(',', '').strip()
#         try:
#             return float(s)
#         except:
#             return 0.0


# def settle_transactions(csv_path, bank_name="BANK", min_peer_txn=1.0):
#     # 1) Load ledger
#     df = pd.read_csv(csv_path)

#     # 2) Load payment methods
#     project_root = os.path.dirname(os.path.dirname(os.path.abspath(csv_path)))
#     pm_path = None
#     for d in ("Payment Types", "Payment Type"):
#         candidate = os.path.join(project_root, d, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break
#     if pm_path is None:
#         raise FileNotFoundError("Payment Methods.csv not found under Payment Type(s)/")
#     pm_df = pd.read_csv(pm_path)

#     # full list for handle selection; matching apps skip Cashapp
#     apps = ["Venmo", "Zelle", "Cashapp", "ApplePay"]
#     match_apps = ["Venmo", "Zelle", "ApplePay"]

#     # build lookup: discord_key -> pandas Series row or None
#     pm_map = {}
#     for _, row in pm_df.iterrows():
#         raw = str(row["Player Name"]).strip()
#         low = raw.lower()
#         if "(" in raw and ")" in raw:
#             base = raw.split("(", 1)[0].strip().lower()
#             alias = raw.split("(", 1)[1].split(")", 1)[0].strip().lower()
#             pm_map[base] = row
#             pm_map[alias] = row
#         else:
#             pm_map[low] = row

#     # default missing ledger players to None
#     for full in df["Player Name"].dropna().unique():
#         key = str(full).split("(", 1)[0].strip().lower()
#         if key and key not in pm_map:
#             pm_map[key] = None

#     def available_apps(key):
#         row = pm_map.get(key)
#         if row is None:
#             return ["Venmo"]
#         out = []
#         for app in apps:
#             v = row.get(app)
#             if pd.notnull(v) and str(v).strip():
#                 out.append(app)
#         return out or ["Venmo"]

#     def get_handle(key, app):
#         row = pm_map.get(key)
#         if row is None:
#             return ""
#         v = row.get(app)
#         return "" if pd.isnull(v) else str(v).strip()

#     # 3) Build debtor & creditor pools
#     debtors = []
#     creditors = []
#     for _, row in df.iterrows():
#         name = row["Player Name"]
#         key = str(name).split("(", 1)[0].strip().lower()
#         credit_flag = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack = parse_currency(row["Ending Stack"])
#         pl = parse_currency(row["P/L Player"])
#         send_out = parse_currency(row["Send Out"])
#         sent = parse_currency(row["$ Sent"])

#         if not credit_flag and end_stack > 0 and sent > 0:
#             creditors.append({"name": name, "key": key, "amt": sent})
#         elif credit_flag:
#             if pl < 0 and send_out < 0:
#                 debtors.append({"name": name, "key": key, "amt": abs(send_out)})
#             elif pl > 0 and sent > 0:
#                 creditors.append({"name": name, "key": key, "amt": sent})

#     transactions = []

#     # 4) Match within Venmo, Zelle, ApplePay only
#     for app in match_apps:
#         # filter lists
#         d_list = [d for d in debtors if app in available_apps(d["key"])]
#         c_list = [c for c in creditors if app in available_apps(c["key"])]
#         d_list.sort(key=lambda x: x["amt"], reverse=True)
#         c_list.sort(key=lambda x: x["amt"], reverse=True)

#         i = j = 0
#         while i < len(d_list) and j < len(c_list):
#             d = d_list[i]
#             c = c_list[j]
#             x = min(d["amt"], c["amt"])
#             if x < min_peer_txn:
#                 break
#             handle = get_handle(c["key"], app)
#             transactions.append({
#                 "From":   d["name"],
#                 "To":     c["name"],
#                 "Amount": round(x, 2),
#                 "Method": f"{app}: {handle}"
#             })
#             d["amt"] -= x
#             c["amt"] -= x
#             if d["amt"] < 1e-6:
#                 i += 1
#             if c["amt"] < 1e-6:
#                 j += 1

#         # rebuild pools
#         debtors   = [d for d in debtors   if d["amt"] > 1e-6]
#         creditors = [c for c in creditors if c["amt"] > 1e-6]

#     # 5) BANK settles all remaining (including Cashapp)
#     # 5a) BANK → creditors
#     for c in creditors:
#         amt = c["amt"]
#         if amt > 1e-6:
#             # pick creditor's first available handle
#             app, handle = "Venmo", ""
#             row = pm_map.get(c["key"])
#             if row is not None:
#                 for a in apps:
#                     v = row.get(a)
#                     if pd.notnull(v) and str(v).strip():
#                         app, handle = a, str(v).strip()
#                         break
#             transactions.append({
#                 "From":   bank_name,
#                 "To":     c["name"],
#                 "Amount": round(amt, 2),
#                 "Method": f"{app}: {handle}"
#             })

#     # 5b) debtors → BANK
#     for d in debtors:
#         amt = d["amt"]
#         if amt > 1e-6:
#             app, handle = "Venmo", ""
#             row = pm_map.get(d["key"])
#             if row is not None:
#                 for a in apps:
#                     v = row.get(a)
#                     if pd.notnull(v) and str(v).strip():
#                         app, handle = a, str(v).strip()
#                         break
#             transactions.append({
#                 "From":   d["name"],
#                 "To":     bank_name,
#                 "Amount": round(amt, 2),
#                 "Method": f"{app}: {handle}"
#             })

#     # 6) Write out CSV
#     out_df = pd.DataFrame(transactions, columns=["From", "To", "Amount", "Method"])
#     tx_dir = os.path.join(project_root, "Transactions")
#     os.makedirs(tx_dir, exist_ok=True)
#     base = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(tx_dir, f"{base}_transactions.csv")
#     out_df.to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(transactions)} transactions to:\n    {out_path}")


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — bank handles Cashapp & large sums"
#     )
#     p.add_argument(
#         "--csv", required=True,
#         help='Path to your ledger CSV (e.g. "Ledger Data/6_30_25.csv")'
#     )
#     p.add_argument(
#         "--bank-name", default="BANK",
#         help="Label to use for the bank/host"
#     )
#     p.add_argument(
#         "--min-peer", type=float, default=1.0,
#         help="Minimum peer-to-peer txn amount in dollars"
#     )
#     args = p.parse_args()
#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name,
#         min_peer_txn=args.min_peer
#     )


# if __name__ == "__main__":
#     main()



















# v1.9UPDATED VERSION OF "v1.6 MAKES SOMEONE WITHOUT A SPECIFIC PAYMENT APP PAY ANOTHER PERSON WHO ONLY HAS THAT PAYMENT APP"



# #!/usr/bin/env python3
# """
# Backend/payoutSystem.py

# Reads a Poker Ledger CSV, validates every player against
# Payment Type(s)/Payment Methods.csv (defaulting missing players to Venmo),
# then produces peer-to-peer transactions ≥ $1 (borrowing cents where possible),
# rolling any true “dust” under $1 back to the BANK for its final settlements,
# and appending each receiver’s payment handle.
# """

# import argparse
# import os
# import sys
# import itertools
# from collections import defaultdict
# import pandas as pd


# def parse_currency(val):
#     if pd.isnull(val):
#         return 0.0
#     if isinstance(val, (int, float)):
#         return float(val)
#     s = str(val).replace('$', '').replace(',', '').strip()
#     try:
#         return float(s)
#     except ValueError:
#         return 0.0


# def settle_transactions(csv_path, bank_name="BANK", min_peer_txn=1.0):
#     # 1) Load ledger CSV
#     df = pd.read_csv(csv_path)

#     # 2) Load Payment Methods, build pm_map: discord → full row or None
#     abs_csv      = os.path.abspath(csv_path)
#     ledger_dir   = os.path.dirname(abs_csv)
#     project_root = os.path.dirname(ledger_dir)

#     pm_path = None
#     for dname in ("Payment Types", "Payment Type"):
#         candidate = os.path.join(project_root, dname, "Payment Methods.csv")
#         if os.path.isfile(candidate):
#             pm_path = candidate
#             break

#     if pm_path is None:
#         print("✗ Error: cannot find Payment Methods.csv. Looked in:")
#         print(f"  • {os.path.join(project_root, 'Payment Types', 'Payment Methods.csv')}")
#         print(f"  • {os.path.join(project_root, 'Payment Type',  'Payment Methods.csv')}")
#         sys.exit(1)

#     pm_df = pd.read_csv(pm_path)
#     pm_map = {}
#     for _, row in pm_df.iterrows():
#         entry = str(row["Player Name"]).strip()
#         lower = entry.lower()
#         if "(" in entry and ")" in entry:
#             before = entry.split("(", 1)[0].strip().lower()
#             inside = entry.split("(", 1)[1].split(")", 1)[0].strip().lower()
#             pm_map[before] = row
#             pm_map[inside] = row
#         else:
#             pm_map[lower] = row

#     # 3) Warn about missing players but default them to Venmo
#     missing = []
#     for full in df["Player Name"].unique():
#         if pd.isnull(full):
#             continue
#         full_str = str(full).strip()
#         if not full_str:
#             continue
#         discord = full_str.split("(", 1)[0].strip().lower()
#         if discord not in pm_map:
#             missing.append(discord)
#             pm_map[discord] = None

#     if missing:
#         print("⚠ Warning: no payment methods found for these players; defaulting them to Venmo:")
#         for name in missing:
#             print(f"  • {name}")

#     # 4) Build raw debtor & creditor pools
#     base_debtors   = []
#     base_creditors = []
#     for _, row in df.iterrows():
#         name       = row["Player Name"]
#         credit_yes = str(row["Credit?"]).strip().lower() == "yes"
#         end_stack  = parse_currency(row["Ending Stack"])
#         pl         = parse_currency(row["P/L Player"])
#         send_out   = parse_currency(row["Send Out"])
#         sent       = parse_currency(row["$ Sent"])

#         if not credit_yes and end_stack > 0 and sent > 0:
#             base_creditors.append([name, sent])
#         elif credit_yes:
#             if pl < 0 and abs(send_out) > 0:
#                 base_debtors.append([name, abs(send_out)])
#             elif pl > 0 and sent > 0:
#                 base_creditors.append([name, sent])

#     # 5) Greedy-match helper
#     def simulate(dr, cr):
#         debtors   = [d.copy() for d in base_debtors]
#         creditors = [c.copy() for c in base_creditors]
#         debtors.sort(key=lambda x: x[1], reverse=dr)
#         creditors.sort(key=lambda x: x[1], reverse=cr)

#         matches = []
#         i = j = 0
#         while i < len(debtors) and j < len(creditors):
#             dn, da = debtors[i]
#             cn, ca = creditors[j]
#             x = min(da, ca)
#             matches.append({"From": dn, "To": cn, "Amount": round(x, 2)})
#             debtors[i][1]   -= x
#             creditors[j][1] -= x
#             if debtors[i][1]   < 1e-6:
#                 i += 1
#             if creditors[j][1] < 1e-6:
#                 j += 1

#         leftover_bank = sum(1 for k in range(i, len(debtors))   if debtors[k][1]   > 1e-6)
#         leftover_bank += sum(1 for k in range(j, len(creditors)) if creditors[k][1] > 1e-6)
#         return leftover_bank, len(matches) + leftover_bank, matches, debtors, creditors, i, j

#     # 6) Pick best sort-order strategy
#     best = None
#     for dr, cr in itertools.product([True, False], repeat=2):
#         lb, tt, m, dl, cl, di, cj = simulate(dr, cr)
#         if best is None or (lb, tt) < best[0]:
#             best = ((lb, tt), dr, cr, m, dl, cl, di, cj)

#     (_, _), debt_rev, cred_rev, matches, debtors, creditors, idx_d, idx_c = best

#     # 7) Split any < $1 peer matches by borrowing cents
#     to_bank = []
#     debtor_matches = defaultdict(list)
#     for i, tx in enumerate(matches):
#         debtor_matches[tx["From"]].append(i)

#     for debtor, idxs in debtor_matches.items():
#         for idx in list(idxs):
#             amt = matches[idx]["Amount"]
#             if amt < min_peer_txn:
#                 need = min_peer_txn - amt
#                 donor = next(
#                     (j for j in idxs if j != idx and matches[j]["Amount"] >= min_peer_txn + need),
#                     None
#                 )
#                 if donor is not None:
#                     matches[donor]["Amount"] = round(matches[donor]["Amount"] - need, 2)
#                     matches[idx]["Amount"]   = round(matches[idx]["Amount"] + need, 2)
#                 else:
#                     to_bank.append(matches[idx])
#                     matches[idx]["Amount"] = 0.0

#     peer_txns = [tx for tx in matches if tx["Amount"] >= min_peer_txn]

#     # 8) Return any dropped small matches into pools
#     for tx in to_bank:
#         amt = tx["Amount"] or 0.0
#         for d in debtors:
#             if d[0] == tx["From"]:
#                 d[1] += amt
#                 break
#         for c in creditors:
#             if c[0] == tx["To"]:
#                 c[1] += amt
#                 break

#     # 9) Finalize: peer-to-peer ≥ $1, then bank settles all pennies
#     final_txns = list(peer_txns)
#     for name, amt in creditors[idx_c:]:
#         if amt > 1e-6:
#             final_txns.append({"From": bank_name, "To": name, "Amount": round(amt, 2)})
#     for name, amt in debtors[idx_d:]:
#         if amt > 1e-6:
#             final_txns.append({"From": name, "To": bank_name, "Amount": round(amt, 2)})

#     # 10) Attach receiver’s payment handle in "Method" column and format message
#     for tx in final_txns:
#         # strip any parenthetical and lowercase for lookup
#         to_key = str(tx["To"]).split("(", 1)[0].strip().lower()
#         row    = pm_map.get(to_key)

#         # default to Venmo if no row
#         platform = "Venmo"
#         handle   = ""

#         if row is not None:
#             for col in ("Venmo", "Zelle", "Cashapp", "ApplePay"):
#                 val = row.get(col, "")
#                 if pd.notnull(val) and str(val).strip():
#                     platform = col
#                     handle   = str(val).strip()
#                     break

#         amt = tx["Amount"]
#         if handle:
#             tx["Method"] = f"Pay user {amt:.2f} on {platform}: {handle}"
#         else:
#             tx["Method"] = f"Pay user {amt:.2f} on {platform}"

#     # 11) Write out CSV with Method
#     out_dir = os.path.join(project_root, "Transactions")
#     os.makedirs(out_dir, exist_ok=True)
#     base     = os.path.splitext(os.path.basename(csv_path))[0]
#     out_path = os.path.join(out_dir, f"{base}_transactions.csv")
#     pd.DataFrame(final_txns).to_csv(out_path, index=False)

#     print(f"[✓] Wrote {len(final_txns)} transactions "
#           f"(bank-limited strategy dr={debt_rev}, cr={cred_rev}) to:\n    {out_path}")


# def main():
#     p = argparse.ArgumentParser(
#         description="Poker Ledger Payout System — outputs receiver’s payment handle"
#     )
#     p.add_argument("--csv",      required=True,
#                    help="Path to your ledger CSV (e.g. 'Ledger Data/7_2_25.csv')")
#     p.add_argument("--bank-name", default="BANK",
#                    help="Label for host/bank on any settlements")
#     p.add_argument("--min-peer",  type=float, default=1.0,
#                    help="Minimum peer-to-peer txn amount ($1 by default)")
#     args = p.parse_args()

#     settle_transactions(
#         args.csv,
#         bank_name=args.bank_name,
#         min_peer_txn=args.min_peer
#     )


# if __name__ == "__main__":
#     main()
