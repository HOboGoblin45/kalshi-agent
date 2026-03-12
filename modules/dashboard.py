"""Web dashboard for monitoring agent activity."""
import json, threading
import http.server

from modules.config import CFG, SHARED, SHARED_LOCK, log

DASHBOARD_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Kalshi Agent v6</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Instrument+Sans:wght@400;600;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Instrument Sans',sans-serif;background:#06090f;color:#e0e6f0;min-height:100vh}
.hdr{background:#0c1118;border-bottom:1px solid #1a2536;padding:14px 24px;display:flex;align-items:center;justify-content:space-between}
.hdr h1{font-size:20px;font-weight:700;background:linear-gradient(135deg,#e8b94a,#f5d78e);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr .v{font-size:10px;color:#556a85;margin-left:8px}
.hdr .rt{display:flex;align-items:center;gap:14px}
.env{font-family:'IBM Plex Mono',monospace;font-size:11px;padding:3px 10px;border-radius:10px;font-weight:600}
.env.PROD{background:rgba(248,113,113,.12);color:#f87171;border:1px solid rgba(248,113,113,.2)}
.env.DEMO{background:rgba(96,165,250,.12);color:#60a5fa}
.bal{font-family:'IBM Plex Mono',monospace;font-size:15px;font-weight:600;color:#34d399}
.tw{display:flex;align-items:center;gap:10px}
.tl{font-size:13px;font-weight:600}
.tb{width:56px;height:28px;border-radius:14px;border:none;cursor:pointer;position:relative;transition:.3s}
.tb.on{background:#34d399}.tb.off{background:#4a5568}
.tb::after{content:'';position:absolute;width:22px;height:22px;border-radius:50%;background:#fff;top:3px;transition:.3s}
.tb.on::after{left:31px}.tb.off::after{left:3px}
.main{max-width:1100px;margin:0 auto;padding:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}
.card{background:#0c1118;border:1px solid #1a2536;border-radius:8px;padding:14px}
.card .cl{font-size:10px;color:#556a85;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.card .cv{font-family:'IBM Plex Mono',monospace;font-size:18px;font-weight:600}
.green{color:#34d399}.gold{color:#e8b94a}.red{color:#f87171}.blue{color:#60a5fa}.white{color:#e0e6f0}
.sect{background:#0c1118;border:1px solid #1a2536;border-radius:8px;margin-bottom:16px;overflow:hidden}
.sect h2{font-size:13px;font-weight:600;padding:12px 16px;border-bottom:1px solid #1a2536;color:#8a9bb5}
.lb{max-height:280px;overflow-y:auto;padding:8px 12px;font-family:'IBM Plex Mono',monospace;font-size:11px}
.ll{padding:2px 0;display:flex;gap:8px;border-bottom:1px solid rgba(26,37,54,.4)}
.lt{color:#556a85;min-width:55px}.lm{color:#8a9bb5;word-break:break-word}
.lm.WARNING{color:#e8b94a}.lm.ERROR{color:#f87171}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 12px;font-size:10px;color:#556a85;text-transform:uppercase;border-bottom:1px solid #1a2536}
td{padding:7px 12px;border-bottom:1px solid #0f1520;font-family:'IBM Plex Mono',monospace;font-size:11px}
tr:hover td{background:#0f1520}
.yes{color:#34d399}.no{color:#f87171}
.ft{font-size:11px;color:#3a4a60;padding:10px 16px;text-align:center;border-top:1px solid #1a2536}
.paused{background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.25);color:#f87171;padding:12px;border-radius:8px;text-align:center;margin-bottom:16px;font-weight:600}
.debate-tag{font-size:9px;padding:2px 5px;border-radius:3px;font-weight:600;margin-left:4px}
.debate-tag.bull{background:rgba(52,211,153,.15);color:#34d399}
.debate-tag.bear{background:rgba(248,113,113,.15);color:#f87171}
</style></head><body>
<div class="hdr">
<div><h1 style="display:inline">Kalshi AI Agent</h1><span class="v">v6 -- Cross-Platform Arbitrage</span></div>
<div class="rt"><span class="env" id="env">--</span><span class="bal" id="bal">$0.00</span>
<div class="tw"><span class="tl" id="tL">ON</span><button class="tb on" id="tB" onclick="toggle()"></button></div></div></div>
<div class="main">

<div id="pB" class="paused" style="display:none">PAUSED -- daily loss limit</div>
<div class="cards">
<div class="card"><div class="cl">Status</div><div class="cv gold" id="cS">--</div></div>
<div class="card"><div class="cl">Kalshi</div><div class="cv green" id="cBK">$0</div></div>
<div class="card"><div class="cl">Polymarket</div><div class="cv green" id="cBP">$0</div></div>
<div class="card"><div class="cl">Combined</div><div class="cv green" id="cBC">$0</div></div>
<div class="card"><div class="cl">Scans</div><div class="cv blue" id="cSc">0</div></div>
<div class="card"><div class="cl">Trades Today</div><div class="cv white" id="cD">0/15</div></div>
<div class="card"><div class="cl">Exposure</div><div class="cv white" id="cE">$0</div></div>
<div class="card"><div class="cl">Today P&L</div><div class="cv" id="cP">$0</div></div>
<div class="card"><div class="cl">Lifetime</div><div class="cv white" id="cL">0</div></div>
<div class="card"><div class="cl">Win Rate</div><div class="cv green" id="cW">--</div></div>
<div class="card"><div class="cl">Arb Opps</div><div class="cv gold" id="cA">0</div></div>
<div class="card"><div class="cl">Cross-Arb</div><div class="cv gold" id="cCA">0</div></div>
</div>
<div class="sect"><h2>Trade History (Cross-Platform)</h2>
<table><thead><tr><th>Time</th><th>Plat</th><th>Market</th><th>Side</th><th>Qty</th><th>Price</th><th>Cost</th><th>Edge</th><th>Conf</th><th>Bull/Bear</th><th>Evidence</th></tr></thead>
<tbody id="tbl"><tr><td colspan="10" style="text-align:center;color:#556a85;padding:20px">No trades yet</td></tr></tbody></table></div>
<div class="sect"><h2>Activity Log</h2><div class="lb" id="lB"></div></div>
<div class="ft" id="ft">--</div></div>
<script>
async function poll(){try{
const r=await fetch('/api/state');const d=await r.json();
const e=document.getElementById('env');e.textContent=d.environment;e.className='env '+d.environment;
const combined=(d.balance+(d.poly_balance||0));
document.getElementById('bal').textContent='$'+combined.toFixed(2);
document.getElementById('cBK').textContent='$'+d.balance.toFixed(2);
document.getElementById('cBP').textContent='$'+(d.poly_balance||0).toFixed(2);
document.getElementById('cBC').textContent='$'+combined.toFixed(2);
document.getElementById('cS').textContent=d.status;
document.getElementById('cSc').textContent=d.scan_count;
document.getElementById('cD').textContent=d.risk.day_trades+'/'+d.max_daily;
document.getElementById('cE').textContent=d.risk.exposure;
document.getElementById('cP').textContent=d.risk.day_pnl;
document.getElementById('cL').textContent=d.risk.total;
document.getElementById('cW').textContent=d.risk.win_rate;
document.getElementById('cA').textContent=d.arb_opps;
document.getElementById('cCA').textContent=d.cross_arb_opps||0;
const b=document.getElementById('tB'),l=document.getElementById('tL');
b.className='tb '+(d.enabled?'on':'off');l.textContent=d.enabled?'ON':'OFF';
document.getElementById('pB').style.display=d.risk.paused?'block':'none';

const polyTag=d.poly_enabled?' | Polymarket: ON':'';
document.getElementById('ft').textContent='Last: '+d.last_scan+' | Next: '+d.next_scan+' | Arb: '+d.scan_interval+'m | AI: '+(d.ai_interval||15)+'m | v6 Cross-Platform'+polyTag;
const tb=document.getElementById('tbl');
if(d.trades&&d.trades.length){tb.innerHTML=d.trades.slice().reverse().slice(0,20).map(t=>{
const sc=t.side==='yes'?'yes':'no';
const bp=t.bull_prob||'?'; const brp=t.bear_prob||'?';
const plat=(t.platform||'kalshi').slice(0,1).toUpperCase();
const platColor=plat==='P'?'#a78bfa':plat==='C'?'#e8b94a':'#60a5fa';
return '<tr><td>'+t.time.slice(5,16)+'</td><td style="color:'+platColor+';font-weight:600">'+plat+'</td><td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;font-family:Instrument Sans,sans-serif;font-size:11px">'+(t.title||t.ticker).slice(0,35)+'</td><td class="'+sc+'">'+t.side.toUpperCase()+'</td><td>'+t.contracts+'</td><td>'+t.price_cents+'c</td><td>$'+t.cost.toFixed(2)+'</td><td>'+t.edge+'%</td><td>'+t.confidence+'%</td><td><span class="debate-tag bull">B:'+bp+'%</span><span class="debate-tag bear">R:'+brp+'%</span></td><td style="font-family:Instrument Sans;font-size:10px;color:#8a9bb5;max-width:160px;overflow:hidden;text-overflow:ellipsis">'+(t.evidence||'').slice(0,45)+'</td></tr>';}).join('');}
const lb=document.getElementById('lB');
lb.innerHTML=d.log.slice().reverse().slice(0,100).map(l=>'<div class="ll"><span class="lt">'+l.time+'</span><span class="lm '+l.level+'">'+l.msg+'</span></div>').join('');
}catch(e){}}
async function toggle(){await fetch('/api/toggle',{method:'POST'});poll();}
setInterval(poll,3000);poll();
</script></body></html>"""


class DashHandler(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/': self._html(DASHBOARD_HTML)
        elif self.path == '/api/state': self._json(self._state())
        elif self.path == '/api/markets': self._json(self._markets())
        elif self.path == '/api/positions': self._json(self._positions())
        elif self.path == '/api/trades': self._json(self._trades())
        else: self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == '/api/toggle':
            with SHARED_LOCK:
                SHARED["enabled"] = not SHARED["enabled"]
                enabled = SHARED["enabled"]
            log.info(f"Agent {'ENABLED' if enabled else 'DISABLED'} via dashboard")
            self._json({"enabled": enabled})
        else: self.send_response(404); self.end_headers()

    def _html(self, c):
        d = c.encode(); self.send_response(200); self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)

    def _json(self, obj):
        d = json.dumps(obj, default=str).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers(); self.wfile.write(d)

    def _state(self):
        risk = SHARED.get("_risk_summary", {"total": 0, "wins": 0, "losses": 0, "win_rate": "--",
            "wagered": "$0", "day_trades": 0, "day_pnl": "$0", "exposure": "$0", "paused": False})
        return {"enabled": SHARED["enabled"], "status": SHARED["status"], "balance": SHARED["balance"],
            "poly_balance": SHARED.get("poly_balance", 0), "poly_enabled": SHARED.get("poly_enabled", False),
            "environment": CFG["environment"].upper(), "risk": risk, "trades": SHARED.get("_trades", [])[-20:],
            "log": SHARED["log_lines"][-100:], "last_scan": SHARED["last_scan"], "next_scan": SHARED["next_scan"],
            "max_daily": CFG["max_daily_trades"], "scan_count": SHARED["scan_count"],
            "scan_interval": CFG["scan_interval_minutes"],
            "ai_interval": CFG["scan_interval_minutes"] * CFG.get("ai_scan_interval_multiplier", 5),
            "arb_opps": SHARED["_arb_opportunities"],
            "cross_arb_opps": SHARED.get("_cross_arb_opportunities", 0),
            "quickflip_active": SHARED.get("_quickflip_active", 0)}

    def _markets(self):
        return SHARED.get("_cached_markets", [])

    def _positions(self):
        return SHARED.get("_positions", [])

    def _trades(self):
        return SHARED.get("_trades", [])

    def log_message(self, *a): pass


def start_dashboard():
    port = CFG.get("dashboard_port", 9000)
    srv = http.server.HTTPServer(("0.0.0.0", port), DashHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info(f"Dashboard: http://localhost:{port}")
