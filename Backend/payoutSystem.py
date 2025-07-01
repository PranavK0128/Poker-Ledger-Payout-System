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







"""
Backend/payoutSystem.py

Reads a Poker Ledger CSV, identifies who owes money and who is owed,
then produces peer-to-peer transactions >= $1, and rolls any smaller 
amounts back to the BANK, so no player is ever asked to send under $1.
The BANK’s own settlements will include exact pennies to close out.
"""

import argparse
import os
import itertools
import pandas as pd


def parse_currency(val):
    if pd.isnull(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def settle_transactions(csv_path, bank_name="BANK", min_peer_txn=1.0):
    df = pd.read_csv(csv_path)

    # 1) Build raw debtor & creditor pools (same as before)
    base_debtors, base_creditors = [], []
    for _, row in df.iterrows():
        name       = row['Player Name']
        credit_yes = str(row['Credit?']).strip().lower() == 'yes'
        end_stack  = parse_currency(row['Ending Stack'])
        pl         = parse_currency(row['P/L Player'])
        send_out   = parse_currency(row['Send Out'])
        sent       = parse_currency(row['$ Sent'])

        if not credit_yes and end_stack > 0 and sent > 0:
            base_creditors.append([name, sent])
        elif credit_yes:
            if pl < 0 and abs(send_out) > 0:
                base_debtors.append([name, abs(send_out)])
            elif pl > 0 and sent > 0:
                base_creditors.append([name, sent])

    # 2) Greedy match helper
    def simulate(dr, cr):
        debtors   = [d.copy() for d in base_debtors]
        creditors = [c.copy() for c in base_creditors]
        debtors.sort(key=lambda x: x[1], reverse=dr)
        creditors.sort(key=lambda x: x[1], reverse=cr)

        matches = []
        i = j = 0
        while i < len(debtors) and j < len(creditors):
            dn, da = debtors[i]
            cn, ca = creditors[j]
            x = min(da, ca)
            matches.append({'From': dn, 'To': cn, 'Amount': round(x, 2)})
            debtors[i][1]   -= x
            creditors[j][1] -= x
            if debtors[i][1]   < 1e-6: i += 1
            if creditors[j][1] < 1e-6: j += 1

        # count bank txns if we rolled everything sub-$1
        leftover_bank = sum(1 for k in range(i, len(debtors))   if debtors[k][1]   > 1e-6)
        leftover_bank += sum(1 for k in range(j, len(creditors)) if creditors[k][1] > 1e-6)
        total_txns = len(matches) + leftover_bank
        return leftover_bank, total_txns, matches, debtors, creditors, i, j

    # 3) Pick best sort order (bank‐first, then total)
    best = None
    for dr, cr in itertools.product([True, False], repeat=2):
        lb, tt, m, dl, cl, di, cj = simulate(dr, cr)
        if best is None or (lb, tt) < best[0]:
            best = ((lb, tt), dr, cr, m, dl, cl, di, cj)

    (_, _), debt_rev, cred_rev, matches, debtors, creditors, idx_d, idx_c = best

    # 4) **Split up any < $1 peer matches** by borrowing cents from a larger peer match
    to_bank = []  # will hold matches we can’t rescue
    # group match indices by debtor
    from collections import defaultdict
    debtor_matches = defaultdict(list)
    for i,tx in enumerate(matches):
        debtor_matches[tx['From']].append(i)

    for debtor, idxs in debtor_matches.items():
        # keep looping until no < $1 left or no donors
        for idx in list(idxs):
            amt = matches[idx]['Amount']
            if amt < min_peer_txn:
                need = min_peer_txn - amt
                # find a donor index with >= need + min_peer_txn
                donor = next(
                    (j for j in idxs
                     if j != idx and matches[j]['Amount'] >= min_peer_txn + need),
                    None
                )
                if donor is not None:
                    # borrow 'need' cents
                    matches[donor]['Amount'] = round(matches[donor]['Amount'] - need, 2)
                    matches[idx]['Amount']   = round(matches[idx]['Amount'] + need, 2)
                else:
                    # can’t rescue this small match → send to bank
                    to_bank.append(matches[idx])
                    matches[idx]['Amount'] = 0.0  # drop from peer list

    # collect the surviving peer-to-peer transactions
    peer_txns = [tx for tx in matches
                 if tx['Amount'] >= min_peer_txn]

    # 5) **Return any totally dropped small matches** back to the pools
    for tx in to_bank:
        amt = tx['Amount'] or 0.0
        # restore to debtor
        for d in debtors:
            if d[0] == tx['From']:
                d[1] += amt
                break
        # restore to creditor
        for c in creditors:
            if c[0] == tx['To']:
                c[1] += amt
                break

    # 6) Build final: peer-to-peer ≥ $1, then bank settles **all** leftovers exactly
    final_txns = peer_txns[:]
    # bank → creditors
    for name, amt in creditors[idx_c:]:
        if amt > 1e-6:
            final_txns.append({'From': bank_name, 'To': name, 'Amount': round(amt, 2)})
    # debtors → bank
    for name, amt in debtors[idx_d:]:
        if amt > 1e-6:
            final_txns.append({'From': name, 'To': bank_name, 'Amount': round(amt, 2)})

    # 7) Write CSV (same as before)
    trans_df     = pd.DataFrame(final_txns)
    abs_csv      = os.path.abspath(csv_path)
    ledger_dir   = os.path.dirname(abs_csv)
    project_root = os.path.dirname(ledger_dir)
    out_dir      = os.path.join(project_root, 'Transactions')
    os.makedirs(out_dir, exist_ok=True)

    base     = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(out_dir, f"{base}_transactions.csv")
    trans_df.to_csv(out_path, index=False)

    print(f"[✓] Wrote {len(final_txns)} transactions "
          f"(bank‐limited strategy dr={debt_rev}, cr={cred_rev}) to:\n    {out_path}")


def main():
    p = argparse.ArgumentParser(
        description="Poker Ledger Payout System — peer-to-peer >= $1, BANK handles pennies"
    )
    p.add_argument('--csv',      required=True,
                   help='Path to your ledger CSV (e.g. "Ledger Data/6_25_25.csv")')
    p.add_argument('--bank-name', default="BANK",
                   help='Label for host/bank on any settlements')
    p.add_argument('--min-peer', type=float, default=1.0,
                   help='Minimum peer-to-peer txn amount ($1 by default)')
    args = p.parse_args()

    settle_transactions(
        args.csv,
        bank_name=args.bank_name,
        min_peer_txn=args.min_peer
    )


if __name__ == "__main__":
    main()
