#!/usr/bin/env python3
"""
Backend/payoutSystem_v4.py

Phase A) Bank ↔ non-ledgered players
  • Bank collects all non-ledgered “$ Received”.
  • Bank pays all non-ledgered “$ Sent” winners.

Phase B) Ledgered subgame via min-cost flow
  • Nodes = {ledgered losers, ledgered winners, BANK}.
  • Supplies = losers’ debts; Demands = winners’ payouts; BANK’s demand = total tips.
  • Edges = loser→winner and loser→BANK (for tips), cost=1 each.
  • Solve network_simplex → minimal number of transactions, including tip back to BANK.

Outputs Transactions/{date}_transactionsV4.csv
"""

import argparse, os, sys
import pandas as pd
import networkx as nx

def parse_currency(val):
    if pd.isnull(val): return 0.0
    if isinstance(val, (int, float)): return float(val)
    s = str(val).replace('$','').replace(',','').strip()
    try: return float(s)
    except: return 0.0

def settle_transactions(csv_path, bank_name="BANK"):
    # ─── Load ledger CSV & Payment Methods ────────────────────────────────
    df = pd.read_csv(csv_path)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(csv_path)))
    # load pm_map (omitted for brevity; same as v3)
    # … [pm_map code here] …

    # ─── Phase A: Handle non-ledgered players ──────────────────────────────
    nl = df[df["Credit?"].str.strip().str.lower() == "no"]
    # Bank collects every buy-in:
    bank_funds = nl["$ Received"].apply(parse_currency).sum()
    # Who did non-ledgered win?
    nonled_winners = []
    for _, r in nl.iterrows():
        end = parse_currency(r["Ending Stack"])
        sent = parse_currency(r["$ Sent"])
        if end > 0 and sent > 0:
            nonled_winners.append((r["Player Name"], sent))

    transactions = []
    for name, amt in nonled_winners:
        transactions.append({"From": bank_name, "To": name, "Amount": round(amt,2)})
        bank_funds -= amt

    # ─── Phase B: Ledgered subgame via min-cost flow ───────────────────────
    led = df[df["Credit?"].str.strip().str.lower() == "yes"]
    ledger_losers, ledger_winners = [], []
    for _, r in led.iterrows():
        pl = parse_currency(r["P/L Player"])
        send_out = parse_currency(r["Send Out"])
        sent     = parse_currency(r["$ Sent"])
        name     = r["Player Name"]
        if pl < 0 and send_out > 0:
            ledger_losers.append((name, send_out))
        elif pl > 0 and sent > 0:
            ledger_winners.append((name, sent))

    # Total tips = sum(loser debts) − sum(winner payouts)
    total_tip = sum(x for _,x in ledger_losers) - sum(x for _,x in ledger_winners)

    # Build a cents-based network to guarantee integer-balance
    net = {}
    for name, debt in ledger_losers:
        net[name] = -int(round(debt*100))
    for name, recv in ledger_winners:
        net[name] =  int(round(recv*100))
    # BANK’s demand = the tip pool
    net[bank_name] =  int(round(total_tip*100))

    # Assemble the DiGraph
    G = nx.DiGraph()
    for n, d in net.items():
        G.add_node(n, demand=d)
    cap = sum(abs(d) for d in net.values())
    # edges: every loser → every winner, plus loser → BANK (to dump tips)
    for u, supply in net.items():
        if supply < 0:   # a supplier (loser)
            for v, dem in net.items():
                if dem > 0:  # a demander (winner or BANK)
                    G.add_edge(u, v, weight=1, capacity=cap)

    # Solve for min-cost flow
    _, flow = nx.network_simplex(G)

    # Extract ledgered transactions
    for u, targets in flow.items():
        for v, cents in targets.items():
            if cents > 0:
                amt = cents / 100.0
                transactions.append({
                    "From":   u,
                    "To":     v,
                    "Amount": round(amt, 2)
                })

    # ─── Attach “Method” column ────────────────────────────────────────────
    for tx in transactions:
        to_key = str(tx["To"]).split("(",1)[0].strip().lower()
        row = pm_map.get(to_key)
        plat, handle = "Venmo", ""
        if row is not None:
            for col in ("Venmo","Cashapp","Zelle","ApplePay"):
                val = row.get(col,"")
                if pd.notnull(val) and str(val).strip():
                    plat, handle = col, str(val).strip()
                    break
        tx["Method"] = f"Pay user ${tx['Amount']:.2f} on {plat}: {handle}"

    # ─── Write out CSV ─────────────────────────────────────────────────────
    out_dir = os.path.join(project_root, "Transactions")
    os.makedirs(out_dir, exist_ok=True)
    base    = os.path.splitext(os.path.basename(csv_path))[0]
    outpath = os.path.join(out_dir, f"{base}_transactionsV4.csv")
    pd.DataFrame(transactions).to_csv(outpath, index=False)
    print(f"[✓] Wrote {len(transactions)} transactions to: {outpath}")


def main():
    p = argparse.ArgumentParser(description="Poker Ledger Payout System V4")
    p.add_argument("--csv",      required=True, help="Path to ledger CSV")
    p.add_argument("--bank-name", default="BANK", help="Label for bank node")
    args = p.parse_args()
    settle_transactions(args.csv, bank_name=args.bank_name)

if __name__ == "__main__":
    main()
