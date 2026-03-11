"""Email notifications and weekly performance reports."""
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from modules.config import CFG, log


class Notifier:
    """Send email notifications for trades, alerts, and reports."""

    def __init__(self):
        self.enabled = CFG.get("email_enabled", False)
        self.smtp_server = CFG.get("email_smtp_server", "smtp.gmail.com")
        self.smtp_port = CFG.get("email_smtp_port", 587)
        self.from_addr = CFG.get("email_from", "")
        self.password = CFG.get("email_password", "")
        self.to_addr = CFG.get("email_to", "")
        if self.enabled and (not self.from_addr or not self.password or not self.to_addr):
            log.warning("Email enabled but missing from/password/to -- disabling")
            self.enabled = False
        if self.enabled:
            try:
                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as s:
                    s.starttls()
                    s.login(self.from_addr, self.password)
                log.info(f"Email notifications: ON -> {self.to_addr} (SMTP verified)")
            except Exception as e:
                log.warning(f"Email SMTP login failed: {e} -- disabling email notifications")
                self.enabled = False

    def send(self, subject, body):
        if not self.enabled: return
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_addr
            msg["To"] = self.to_addr
            msg["Subject"] = f"[Kalshi Agent] {subject}"
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as s:
                s.starttls()
                s.login(self.from_addr, self.password)
                s.send_message(msg)
            log.info(f"Email sent: {subject}")
        except Exception as e:
            log.warning(f"Email failed: {e}")

    def notify_trade(self, trade_info):
        if not CFG.get("notify_on_trade", True): return
        side = trade_info.get("side", "?").upper()
        tk = trade_info.get("ticker", "?")
        title = trade_info.get("title", "")[:40]
        contracts = trade_info.get("contracts", 0)
        price = trade_info.get("price_cents", 0)
        cost = trade_info.get("cost", 0)
        edge = trade_info.get("edge", 0)
        conf = trade_info.get("confidence", 0)
        bull = trade_info.get("bull_prob", 0)
        bear = trade_info.get("bear_prob", 0)
        evidence = trade_info.get("evidence", "")[:100]
        self.send(f"Trade: {side} {contracts}x {tk} @{price}c",
            f"TRADE EXECUTED\n\n"
            f"Market: {title}\nTicker: {tk}\n"
            f"Side: {side}\nContracts: {contracts}\nPrice: {price}c\nCost: ${cost:.2f}\n"
            f"Edge: {edge}%\nConfidence: {conf}%\n"
            f"Bull: {bull}% | Bear: {bear}%\n\n"
            f"Evidence: {evidence}\n\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def notify_exit(self, ticker, title, side, reason, pnl):
        self.send(f"Exit: {ticker} ({reason})",
            f"POSITION EXITED\n\n"
            f"Market: {title}\nTicker: {ticker}\nSide: {side}\n"
            f"Reason: {reason}\nP&L: ${pnl:.2f}\n\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def notify_circuit_breaker(self, day_pnl):
        if not CFG.get("notify_on_circuit_breaker", True): return
        self.send("CIRCUIT BREAKER TRIGGERED",
            f"Daily loss limit reached.\n\nDay P&L: ${day_pnl:.2f}\n"
            f"Limit: ${CFG['max_daily_loss']:.2f}\n\n"
            f"Agent is PAUSED until tomorrow.\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def notify_arbitrage(self, arb_info):
        if not CFG.get("notify_on_arbitrage", True): return
        self.send(f"Arbitrage: {arb_info['ticker']} +{arb_info['profit_cents']:.1f}c",
            f"ARBITRAGE EXECUTED\n\n"
            f"Market: {arb_info.get('title', '')}\nTicker: {arb_info['ticker']}\n"
            f"YES: {arb_info['yes_price']:.0f}c + NO: {arb_info['no_price']:.0f}c = {arb_info['total_cost']:.0f}c\n"
            f"Guaranteed profit: {arb_info['profit_cents']:.1f}c per contract\n\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def send_report(self, report_text):
        self.send(f"Weekly Performance Report -- {datetime.date.today().strftime('%B %d, %Y')}", report_text)


class PerformanceReporter:
    """Generate weekly performance reports from trade history."""

    def __init__(self, risk, notifier):
        self.risk = risk
        self.notifier = notifier
        self.last_report_date = None

    def should_report(self):
        now = datetime.datetime.now()
        target_day = CFG.get("report_day", "sunday").lower()
        target_hour = CFG.get("report_hour", 20)
        days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6}
        if now.weekday() != days.get(target_day, 6): return False
        if now.hour != target_hour: return False
        if self.last_report_date == now.date(): return False
        return True

    def generate_report(self):
        now = datetime.datetime.now()
        week_ago = now - datetime.timedelta(days=7)
        all_trades = self.risk.trades
        week_trades = []
        for t in all_trades:
            try:
                tt = datetime.datetime.fromisoformat(t["time"])
                if tt >= week_ago: week_trades.append(t)
            except Exception: continue

        total = len(week_trades)
        wins = sum(1 for t in week_trades if t.get("status") == "win")
        losses = sum(1 for t in week_trades if t.get("status") == "loss")
        still_open = sum(1 for t in week_trades if t.get("status") == "open")
        total_wagered = sum(t.get("cost", 0) for t in week_trades)
        total_pnl = sum(t.get("pnl", 0) for t in week_trades if t.get("pnl") is not None)

        cat_stats = {}
        for t in week_trades:
            cat = "unknown"
            title_lower = (t.get("title", "") + " " + t.get("ticker", "")).lower()
            for cat_name, cat_kws in CFG.get("category_rules", {}).items():
                if any(kw in title_lower for kw in cat_kws):
                    cat = cat_name; break
            if cat not in cat_stats: cat_stats[cat] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0}
            cat_stats[cat]["trades"] += 1
            if t.get("status") == "win": cat_stats[cat]["wins"] += 1
            if t.get("status") == "loss": cat_stats[cat]["losses"] += 1
            cat_stats[cat]["pnl"] += t.get("pnl", 0) or 0

        settled = [t for t in week_trades if t.get("pnl") is not None]
        best = max(settled, key=lambda t: t.get("pnl", 0)) if settled else None
        worst = min(settled, key=lambda t: t.get("pnl", 0)) if settled else None

        avg_edge = sum(abs(t.get("edge", 0)) for t in week_trades) / total if total else 0
        avg_conf = sum(t.get("confidence", 0) for t in week_trades) / total if total else 0
        avg_spread = sum(abs(t.get("bull_prob", 50) - t.get("bear_prob", 50)) for t in week_trades) / total if total else 0

        lines = [
            f"KALSHI AI AGENT -- WEEKLY PERFORMANCE REPORT",
            f"Period: {week_ago.strftime('%B %d')} -- {now.strftime('%B %d, %Y')}",
            f"{'=' * 50}", "",
            f"SUMMARY",
            f"  Total trades: {total}",
            f"  Wins: {wins} | Losses: {losses} | Open: {still_open}",
            f"  Win rate: {wins / (wins + losses) * 100:.0f}%" if wins + losses > 0 else "  Win rate: N/A",
            f"  Total wagered: ${total_wagered:.2f}",
            f"  Net P&L: ${total_pnl:.2f}",
            f"  ROI: {total_pnl / total_wagered * 100:.1f}%" if total_wagered > 0 else "  ROI: N/A",
            "",
            f"DEBATE QUALITY",
            f"  Avg edge claimed: {avg_edge:.1f}%",
            f"  Avg confidence: {avg_conf:.0f}%",
            f"  Avg bull-bear spread: {avg_spread:.0f}% (lower = more agreement = better)",
            "",
        ]

        if cat_stats:
            lines.append("CATEGORY BREAKDOWN")
            for cat, s in sorted(cat_stats.items(), key=lambda x: x[1]["trades"], reverse=True):
                wr = f"{s['wins'] / (s['wins'] + s['losses']) * 100:.0f}%" if s['wins'] + s['losses'] > 0 else "N/A"
                lines.append(f"  {cat}: {s['trades']} trades, {wr} win rate, ${s['pnl']:.2f} P&L")
            lines.append("")

        if best and best.get("pnl", 0) > 0:
            lines.append(f"BEST TRADE: {best.get('title', '')[:40]} -- ${best['pnl']:.2f}")
        if worst and worst.get("pnl", 0) < 0:
            lines.append(f"WORST TRADE: {worst.get('title', '')[:40]} -- ${worst['pnl']:.2f}")
        lines.append("")

        all_wins = sum(1 for t in all_trades if t.get("status") == "win")
        all_losses = sum(1 for t in all_trades if t.get("status") == "loss")
        all_pnl = sum(t.get("pnl", 0) for t in all_trades if t.get("pnl") is not None)
        lines.extend([
            f"LIFETIME",
            f"  Total trades: {len(all_trades)}",
            f"  Win rate: {all_wins / (all_wins + all_losses) * 100:.0f}%" if all_wins + all_losses > 0 else "  Win rate: N/A",
            f"  Net P&L: ${all_pnl:.2f}",
            "", f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        ])
        return "\n".join(lines)

    def maybe_send_report(self):
        if not self.should_report(): return
        self.last_report_date = datetime.date.today()
        report = self.generate_report()
        report_file = CFG.get("report_file", "kalshi-weekly-report.txt")
        try:
            with open(report_file, "w") as f: f.write(report)
            log.info(f"Weekly report saved to {report_file}")
        except Exception as e:
            log.warning(f"Failed to save weekly report: {e}")
        self.notifier.send_report(report)
        log.info("Weekly performance report generated and emailed")

    def run_loop(self, stop_event):
        while not stop_event.is_set():
            try: self.maybe_send_report()
            except Exception as e: log.warning(f"Report error: {e}")
            stop_event.wait(3600)
