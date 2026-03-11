#!/usr/bin/env python3
"""
Fee-aware fractional Kelly Criterion position sizing.

Usage:
  python kelly.py --probability 75 --price-cents 60 --bankroll 40 --max-bet 5 --fee 0.07
  python kelly.py --probability 85 --price-cents 72 --bankroll 50 --max-bet 5 --fee 0.07 --fraction 0.25
"""
import argparse, json

def kelly(prob_pct, price_cents, bankroll, max_bet, fee_per_contract=0.07, fraction=0.20):
    """
    Calculate fee-aware fractional Kelly bet size.

    Args:
        prob_pct: Our estimated probability (1-99)
        price_cents: Contract price in cents (1-99)
        bankroll: Available capital in dollars
        max_bet: Maximum bet size in dollars
        fee_per_contract: Taker fee per contract in dollars
        fraction: Kelly fraction (0.20 = 20% Kelly, conservative)

    Returns:
        dict with contracts, cost, fees, net_profit_if_correct, roi, ev_per_contract
    """
    p = prob_pct / 100.0
    price = price_cents / 100.0
    fee = fee_per_contract

    # Win: gain (1 - price) minus fee
    # Lose: lose price plus fee
    win_payoff = (1.0 - price) - fee
    lose_cost = price + fee

    if win_payoff <= 0:
        return {"contracts":0, "reason":"Cannot profit after fees (win payoff <= 0)",
                "win_payoff":round(win_payoff,4), "lose_cost":round(lose_cost,4)}

    # Expected value per contract
    ev = p * win_payoff - (1 - p) * lose_cost
    if ev <= 0:
        return {"contracts":0, "reason":f"Negative EV after fees (EV={ev:.4f})",
                "ev_per_contract":round(ev,4), "win_payoff":round(win_payoff,4)}

    # Kelly fraction
    b = win_payoff / lose_cost
    q = 1 - p
    kf = max(0, ((b * p - q) / b) * fraction) if b > 0 else 0

    # Convert to contracts
    bet = min(kf * bankroll, max_bet)
    total_per = price + fee
    contracts = max(1, int(bet / total_per)) if bet >= total_per else 0

    while contracts > 0 and contracts * total_per > max_bet:
        contracts -= 1

    if contracts == 0:
        return {"contracts":0, "reason":"Bet size too small for even 1 contract",
                "kelly_fraction":round(kf,4), "ev_per_contract":round(ev,4)}

    cost = round(contracts * price, 2)
    fees = round(contracts * fee, 2)
    gross_profit = round(contracts * (1.0 - price), 2)
    net_profit = round(gross_profit - fees, 2)
    total_cost = round(cost + fees, 2)
    roi = round(net_profit / total_cost * 100, 1) if total_cost > 0 else 0

    return {
        "contracts": contracts,
        "cost": cost,
        "fees": fees,
        "total_cost": total_cost,
        "gross_profit_if_correct": gross_profit,
        "net_profit_if_correct": net_profit,
        "roi_if_correct": f"{roi}%",
        "max_loss": total_cost,
        "ev_per_contract": round(ev, 4),
        "kelly_fraction": round(kf, 4),
        "probability": prob_pct,
        "price_cents": price_cents,
    }

def main():
    ap = argparse.ArgumentParser(description="Fee-Aware Kelly Criterion")
    ap.add_argument("--probability", type=float, required=True, help="Your probability estimate (1-99)")
    ap.add_argument("--price-cents", type=int, required=True, help="Contract price in cents (1-99)")
    ap.add_argument("--bankroll", type=float, required=True, help="Available capital ($)")
    ap.add_argument("--max-bet", type=float, default=5.0, help="Max bet size ($)")
    ap.add_argument("--fee", type=float, default=0.07, help="Fee per contract ($)")
    ap.add_argument("--fraction", type=float, default=0.20, help="Kelly fraction (0.20 = conservative)")
    args = ap.parse_args()

    result = kelly(args.probability, args.price_cents, args.bankroll, args.max_bet, args.fee, args.fraction)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
