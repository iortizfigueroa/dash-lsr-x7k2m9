#!/usr/bin/env python3
"""GitHub Actions runner: fetch Airtable Pedidos → build dashboard HTML → write to index.html.

Environment variables required:
    AIRTABLE_PAT - Airtable Personal Access Token (https://airtable.com/create/tokens)

Optional:
    CUR_MONTH - Override current month (default: today's month)
"""
import base64, json, os, sys, urllib.parse, urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, date

# ----- Config -----
BASE_ID = 'app9U5sz7YS8y9Oit'
TABLE_ID = 'tblKDAT56Z9tX9zvd'
CUR_YEAR = 2026
HERE = os.path.dirname(os.path.abspath(__file__))
BUDGETS_JSON = os.environ.get('BUDGETS_JSON', os.path.join(HERE, 'budgets.json'))
OUTPUT_HTML = os.environ.get('OUTPUT_HTML', os.path.join(HERE, '..', 'index.html'))

# Filter spec (only fetch records we want)
FILTER_FORMULA = (
    "AND("
    "OR({Type of request}='Sale of new device', {Type of request}='Competitors device'),"
    "{Status}!='Pendiente de Aprobación',"
    "{Status}!='Pendiente de Recogida',"
    "{Status}!='Recibido en Gijón',"
    "{Exclude}!=1"
    ")"
)
FIELDS = ['Customer', 'Country', 'Commercial Lead', 'Type of request',
          'Status', 'Fecha Definitiva Reporting', 'Count', 'New chains']

MONTH_NAMES_FULL = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
SPAIN_SUB = {'Sin Vello','Elha','BR Esthetic','Dermasana','Other in Spain'}
ITALY_SUB = {'Epil Point','Elha Italy','Sin Vello Italy','Other in Italy'}
T1_ORDER = ['Sin Vello','Elha','BR Esthetic','Dermasana','Other in Spain','Spain',
            'Epil Point','Elha Italy','Sin Vello Italy','Other in Italy','Italy',
            'New Chains','Germany','Brazil','Mexico','France','Romania','USA','Bulgaria',
            'Poland','India','Turkey','Benelux','Chile','Lithuania','Portugal','Morocco',
            'Others','Total']
T2_STRUCT = [
    ('David Aller', ['Sin Vello','Sin Vello Italy','Dermasana','Other in Spain',
                     'Brazil','Mexico','Romania','Turkey','Bulgaria','Chile','Other countries']),
    ('Oliver Aracil', ['Elha','Elha Italy','BR Esthetic','Other in Italy',
                       'Germany','France','Benelux','Portugal','Morocco','Others in Spain','Other countries']),
    ('Francisco Martinez', ['Poland','India','Lithuania','Others in Spain','Other countries']),
    ('Leaseir', ['Epil Point','USA','New Chains','Others']),
]

# ============================================================
# Airtable fetch
# ============================================================
def fetch_pedidos(pat):
    """Returns list of dicts: customer, country, commercial, type, status, fecha, count, newchains."""
    records = []
    base = f'https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}'
    params = {
        'filterByFormula': FILTER_FORMULA,
        'pageSize': '100',
    }
    for f in FIELDS:
        params.setdefault('fields[]', [])  # not used; can't use []
    # Use multiple "fields[]" entries
    query_parts = [f"filterByFormula={urllib.parse.quote(FILTER_FORMULA)}", "pageSize=100"]
    for f in FIELDS:
        query_parts.append(f"fields%5B%5D={urllib.parse.quote(f)}")
    base_query = '&'.join(query_parts)
    
    offset = None
    while True:
        url = base + '?' + base_query + (f'&offset={offset}' if offset else '')
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {pat}',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
        for r in data.get('records', []):
            fl = r.get('fields', {})
            records.append({
                'customer': fl.get('Customer', '') or '',
                'country': fl.get('Country', '') or '',
                'commercial': fl.get('Commercial Lead', '') or '',
                'status': fl.get('Status', '') or '',
                'fecha': fl.get('Fecha Definitiva Reporting', '') or '',
                'count': float(fl.get('Count') or 0),
                'newchains': bool(fl.get('New chains')),
            })
        offset = data.get('offset')
        if not offset:
            break
    return records

# ============================================================
# Classification & aggregation
# ============================================================
def classify_t1(r):
    if r['newchains']: return 'New Chains'
    c = r['customer'].lower(); cn = r['country']
    if cn == 'Spain':
        if 'sin vello' in c: return 'Sin Vello'
        if 'elha' in c: return 'Elha'
        if 'br esthetic' in c: return 'BR Esthetic'
        if 'dermasana' in c: return 'Dermasana'
        return 'Other in Spain'
    if cn == 'Italy':
        if 'epil point' in c: return 'Epil Point'
        if 'elha' in c: return 'Elha Italy'
        if 'sin vello' in c: return 'Sin Vello Italy'
        return 'Other in Italy'
    if cn in ('Germany','Brazil','Mexico','France','Romania','USA','Bulgaria','Poland',
              'India','Turkey','Benelux','Chile','Lithuania','Portugal','Morocco'):
        return cn
    return 'Others'

def classify_t2(r):
    commercial = r['commercial']; customer = r['customer'].lower(); country = r['country']
    if commercial == 'David Aller':
        bucket = 'David Aller'
        if country == 'Spain' and 'sin vello' in customer: sub = 'Sin Vello'
        elif country == 'Spain' and 'dermasana' in customer: sub = 'Dermasana'
        elif country == 'Spain': sub = 'Other in Spain'
        elif country == 'Italy' and 'sin vello' in customer: sub = 'Sin Vello Italy'
        elif country in ('Brazil','Mexico','Romania','Turkey','Bulgaria','Chile'): sub = country
        else: sub = 'Other countries'
    elif commercial == 'Oliver Aracil':
        bucket = 'Oliver Aracil'
        if country == 'Italy' and 'elha' in customer: sub = 'Elha Italy'
        elif country == 'Italy' and 'br esthetic' in customer: sub = 'BR Esthetic'
        elif country == 'Italy': sub = 'Other in Italy'
        elif country == 'Spain' and 'elha' in customer: sub = 'Elha'
        elif country == 'Spain' and 'br esthetic' in customer: sub = 'BR Esthetic'
        elif country == 'Spain': sub = 'Others in Spain'
        elif country in ('Germany','France','Benelux','Portugal','Morocco'): sub = country
        else: sub = 'Other countries'
    elif commercial in ('Francisco Martínez', 'Francisco Martinez'):
        bucket = 'Francisco Martinez'
        if country == 'Spain': sub = 'Others in Spain'
        elif country in ('Poland','India','Lithuania'): sub = country
        else: sub = 'Other countries'
    else:
        bucket = 'Leaseir'
        if 'epil point' in customer: sub = 'Epil Point'
        elif country == 'USA': sub = 'USA'
        else: sub = 'Others'
    return bucket, sub

def fmt(v):
    if v == int(v): return str(int(v))
    return f"{v:.1f}"

def aggregate(records, cur_month):
    by_month = defaultdict(float)
    by_country_month = defaultdict(lambda: defaultdict(float))
    by_status_cur = defaultdict(float)
    per_customer = defaultdict(float)
    t1 = defaultdict(lambda: defaultdict(float))
    t2 = defaultdict(lambda: defaultdict(float))
    t2_bucket = defaultdict(lambda: defaultdict(float))
    
    for r in records:
        if not r['fecha'] or len(r['fecha']) < 7: continue
        try: y = int(r['fecha'][:4]); m = int(r['fecha'][5:7])
        except: continue
        if y != CUR_YEAR: continue
        if m > cur_month: continue
        period = 'current' if m == cur_month else 'range'
        by_month[m] += r['count']
        by_country_month[r['country'] or 'Unknown'][m] += r['count']
        per_customer[r['customer'] or 'Unknown'] += r['count']
        bucket_t2, sub_t2 = classify_t2(r)
        t2[(bucket_t2, sub_t2)][period] += r['count']
        t2_bucket[bucket_t2][period] += r['count']
        label_t1 = classify_t1(r)
        t1[label_t1][period] += r['count']
        if m == cur_month:
            by_status_cur[r['status']] += r['count']
    
    for p in ('range','current'):
        t1['Spain'][p] = sum(t1[s][p] for s in SPAIN_SUB)
        t1['Italy'][p] = sum(t1[s][p] for s in ITALY_SUB)
        total = sum(t1[k][p] for k in T1_ORDER if k not in ('Spain','Italy','Total') and k not in SPAIN_SUB and k not in ITALY_SUB) + t1['Spain'][p] + t1['Italy'][p]
        t1['Total'][p] = total
    return {
        'by_month': by_month, 'by_country_month': by_country_month,
        'by_status_cur': by_status_cur, 'per_customer': per_customer,
        't1': t1, 't2': t2, 't2_bucket': t2_bucket,
    }

# ============================================================
# HTML rendering (same as before)
# ============================================================
def render_row(row):
    cls = row['cls']
    pct_color = 'red' if row['pct']<25 else 'amber' if row['pct']<50 else 'green'
    pct_width = min(row['pct'], 100)
    return f'''<tr class="row-{cls}" data-label="{row['label'].lower()}">
        <td>{row['label']}</td><td class="r">{fmt(row['ene_prev'])}</td><td class="r">{fmt(row['cur'])}</td>
        <td class="r">{fmt(row['ytd'])}</td><td class="r">{fmt(row['ytd_budget'])}</td>
        <td class="r">{fmt(row['ytd_2025'])}</td><td class="r">{fmt(row['fy26'])}</td>
        <td class="r">{fmt(row['fy25'])}</td>
        <td class="r">{row['pct']}%<span class="pct-bar {pct_color}"><span style="width:{pct_width}%"></span></span></td>
      </tr>'''

def build_html(agg, t1_bud, t2_bud, cur_month):
    cur_month_name = MONTH_NAMES_FULL[cur_month-1]
    prev_month_name = MONTH_NAMES_FULL[cur_month-2] if cur_month > 1 else 'Ene'
    range_label = f"Ene-{prev_month_name}"
    
    # Derived YTD values from monthly arrays
    for label, info in t1_bud.items():
        info['ytd_budget'] = sum(info['monthly_budget_2026'][:cur_month])
        info['ytd_2025'] = sum(info['monthly_fy25'][:cur_month])
    for entry in t2_bud:
        entry['ytd_budget'] = sum(entry['monthly_budget_2026'][:cur_month])
        entry['ytd_2025'] = sum(entry['monthly_fy25'][:cur_month])
    
    t1_total = t1_bud['Total']
    total_ytd = agg['t1']['Total']['range'] + agg['t1']['Total']['current']
    cur_month_total = agg['t1']['Total']['current']
    fy26_budget = t1_total['fy26']; fy25_total = t1_total['fy25']
    ytd_2025 = t1_total['ytd_2025']; ytd_budget = t1_total['ytd_budget']
    pct_completed = round(total_ytd/fy26_budget*100) if fy26_budget else 0
    delta_vs_ly = total_ytd - ytd_2025
    delta_pct = round(delta_vs_ly/ytd_2025*100) if ytd_2025 else 0
    delta_vs_budget = total_ytd - ytd_budget
    delta_vs_budget_pct = round(delta_vs_budget/ytd_budget*100) if ytd_budget else 0
    
    actual_2026_monthly = [agg['by_month'].get(m, 0) for m in range(1, 13)]
    budget_2026 = t1_total['monthly_budget_2026']
    fy25_actual = t1_total['monthly_fy25']
    def cum(arr, only_first_n=None):
        out, s = [], 0
        for i, v in enumerate(arr):
            if only_first_n is not None and i >= only_first_n:
                out.append(None); continue
            s += v; out.append(s)
        return out
    actual_cum = cum(actual_2026_monthly, only_first_n=cur_month)
    budget_cum = cum(budget_2026); fy25_cum = cum(fy25_actual)
    
    def t1_cls(label):
        if label == 'Total': return 'grand'
        if label in SPAIN_SUB or label in ITALY_SUB: return 'sub'
        return 'big'
    t1_rows = []
    for label in T1_ORDER:
        v = agg['t1'].get(label, {})
        rng = v.get('range', 0); cur = v.get('current', 0); ytd = rng + cur
        b = t1_bud.get(label, {})
        fy26 = b.get('fy26', 0); fy25 = b.get('fy25', 0)
        pct = round(ytd/fy26*100) if fy26 else 0
        t1_rows.append({'label':label,'ene_prev':rng,'cur':cur,'ytd':ytd,
            'ytd_budget': b.get('ytd_budget', 0), 'ytd_2025': b.get('ytd_2025', 0),
            'fy26':fy26,'fy25':fy25,'pct':pct,'cls':t1_cls(label)})
    
    t2_rows = []
    idx = 0
    for bucket, subs in T2_STRUCT:
        for s in subs:
            be = t2_bud[idx]; idx += 1
            v = agg['t2'].get((bucket, s), {})
            rng = v.get('range', 0); cur = v.get('current', 0); ytd = rng + cur
            pct = round(ytd/be['fy26']*100) if be['fy26'] else 0
            t2_rows.append({'label':be['label'],'ene_prev':rng,'cur':cur,'ytd':ytd,
                'ytd_budget':be['ytd_budget'],'ytd_2025':be['ytd_2025'],
                'fy26':be['fy26'],'fy25':be['fy25'],'pct':pct,'cls':'sub'})
        be = t2_bud[idx]; idx += 1
        bt = agg['t2_bucket'].get(bucket, {})
        rng = bt.get('range', 0); cur = bt.get('current', 0); ytd = rng + cur
        pct = round(ytd/be['fy26']*100) if be['fy26'] else 0
        t2_rows.append({'label':be['label'],'ene_prev':rng,'cur':cur,'ytd':ytd,
            'ytd_budget':be['ytd_budget'],'ytd_2025':be['ytd_2025'],
            'fy26':be['fy26'],'fy25':be['fy25'],'pct':pct,'cls':'big'})
    be = t2_bud[idx]
    grand = {p: sum(agg['t2_bucket'][b].get(p,0) for b,_ in T2_STRUCT) for p in ('range','current')}
    rng = grand['range']; cur = grand['current']; ytd = rng + cur
    pct = round(ytd/be['fy26']*100) if be['fy26'] else 0
    t2_rows.append({'label':'Total','ene_prev':rng,'cur':cur,'ytd':ytd,
        'ytd_budget':be['ytd_budget'],'ytd_2025':be['ytd_2025'],
        'fy26':be['fy26'],'fy25':be['fy25'],'pct':pct,'cls':'grand'})
    
    comm_ytd = {}
    for bucket, _ in T2_STRUCT:
        bt = agg['t2_bucket'].get(bucket, {})
        comm_ytd[bucket] = bt.get('range', 0) + bt.get('current', 0)
    country_ytd = {c: sum(months.values()) for c, months in agg['by_country_month'].items()}
    top_countries = sorted(country_ytd.items(), key=lambda x: -x[1])[:10]
    top_customers = sorted(agg['per_customer'].items(), key=lambda x: -x[1])[:15]
    status_order = ['Pendiente de Inicio','En proceso de fabricación','En standby',
                    'En proceso de refurbish','Fabricado, pendiente de recogida',
                    'Pendiente enviar a Cliente','Enviado a Cliente (en vuelo)',
                    'Entregado a Cliente']
    
    now = datetime.now().strftime('%d %B %Y, %H:%M UTC')
    t1_table_rows = ''.join(render_row(r) for r in t1_rows)
    t2_table_rows = ''.join(render_row(r) for r in t2_rows)
    
    html = f'''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard Pedidos Leaseir</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Calibri,Arial,sans-serif;background:#f4f6f9;color:#1a2332;padding:20px;min-height:100vh}}.wrap{{max-width:1400px;margin:0 auto}}header{{background:linear-gradient(135deg,#1F4E79 0%,#305496 100%);color:white;padding:24px 28px;border-radius:12px;margin-bottom:24px;box-shadow:0 4px 12px rgba(31,78,121,0.15)}}header h1{{font-size:24px;font-weight:700;margin-bottom:4px}}header .subtitle{{font-size:13px;opacity:0.85}}.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:24px}}.kpi{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,0.05);border-left:4px solid #1F4E79}}.kpi .label{{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px}}.kpi .value{{font-size:32px;font-weight:700;color:#1a2332;line-height:1.1}}.kpi .delta{{font-size:13px;margin-top:6px}}.kpi.green{{border-left-color:#10b981}}.kpi.red{{border-left-color:#ef4444}}.kpi.amber{{border-left-color:#f59e0b}}.delta.up{{color:#10b981}}.delta.down{{color:#ef4444}}.delta.neutral{{color:#6b7280}}.charts-row{{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:24px}}@media (max-width:900px){{.charts-row{{grid-template-columns:1fr}}}}.card{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}}.card h2{{font-size:14px;color:#1F4E79;margin-bottom:16px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px}}.single-card{{margin-bottom:24px}}table.dt{{width:100%;border-collapse:collapse;font-size:13px}}table.dt th{{background:#44546A;color:white;padding:10px 12px;text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:0.3px}}table.dt td{{padding:7px 12px;border-bottom:1px solid #e5e7eb}}table.dt td.r{{text-align:right;font-variant-numeric:tabular-nums}}table.dt tr.row-sub td{{background:#DEEBF7;color:#1a2332}}table.dt tr.row-big td{{background:#1F4E79;color:white;font-weight:600}}table.dt tr.row-grand td{{background:#305496;color:white;font-weight:700;font-size:14px}}.filter-input{{width:100%;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;margin-bottom:12px}}.pct-bar{{display:inline-block;width:50px;height:6px;background:rgba(255,255,255,0.3);border-radius:3px;vertical-align:middle;margin-left:6px;overflow:hidden}}.pct-bar>span{{display:block;height:100%;background:#fff}}tr.row-sub .pct-bar{{background:#cbd5e1}}.footer{{text-align:center;font-size:11px;color:#9ca3af;margin-top:30px;padding:20px}}.tables-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}}@media (max-width:900px){{.tables-grid{{grid-template-columns:1fr}}}}
</style></head>
<body><div class="wrap">
<header><h1>Dashboard Pedidos Leaseir</h1><div class="subtitle">FY 2026 · Actualizado {now}</div></header>
<div class="kpi-grid">
  <div class="kpi"><div class="label">YTD Pedidos</div><div class="value">{fmt(total_ytd)}</div>
    <div class="delta {('up' if delta_vs_ly >= 0 else 'down')}">{'+' if delta_vs_ly>=0 else ''}{fmt(delta_vs_ly)} vs YTD 2025 ({'+' if delta_pct>=0 else ''}{delta_pct}%)</div></div>
  <div class="kpi {('green' if pct_completed >= 33 else 'amber' if pct_completed >= 25 else 'red')}">
    <div class="label">% FY'26 Budget</div><div class="value">{pct_completed}%</div>
    <div class="delta neutral">{fmt(total_ytd)} / {fmt(fy26_budget)}</div></div>
  <div class="kpi {('green' if delta_vs_budget >= 0 else 'red')}">
    <div class="label">vs YTD Budget</div><div class="value">{('+' if delta_vs_budget>=0 else '')}{fmt(delta_vs_budget)}</div>
    <div class="delta {('up' if delta_vs_budget_pct>=0 else 'down')}">{('+' if delta_vs_budget_pct>=0 else '')}{delta_vs_budget_pct}% vs plan ({fmt(ytd_budget)})</div></div>
  <div class="kpi amber"><div class="label">Mes actual ({cur_month_name})</div><div class="value">{fmt(cur_month_total)}</div>
    <div class="delta neutral">Pedidos en curso este mes</div></div>
</div>
<div class="card single-card"><h2>Evolución mensual: Actual 2026 vs Budget 2026 vs Actual 2025</h2><canvas id="evolutionChart" height="80"></canvas></div>
<div class="card single-card"><h2>Evolución acumulada YTD: Actual vs Budget vs Actual 2025</h2><canvas id="cumChart" height="80"></canvas></div>
<div class="charts-row">
  <div class="card"><h2>Top 10 países YTD 2026</h2><canvas id="countriesChart" height="200"></canvas></div>
  <div class="card"><h2>YTD por comercial</h2><canvas id="commercialChart" height="200"></canvas></div>
</div>
<div class="card single-card"><h2>Detalle YTD por país / cadena</h2>
<input type="text" class="filter-input" id="t1Filter" placeholder="Filtrar...">
<div style="overflow-x:auto;"><table class="dt" id="t1Table">
<thead><tr><th>País / Cadena</th><th style="text-align:right;">{range_label}</th><th style="text-align:right;">{cur_month_name}</th><th style="text-align:right;">YTD Actual</th><th style="text-align:right;">YTD Budget</th><th style="text-align:right;">YTD 2025</th><th style="text-align:right;">FY'26 Budget</th><th style="text-align:right;">FY'25</th><th style="text-align:right;">% FY'26</th></tr></thead>
<tbody>{t1_table_rows}</tbody></table></div></div>
<div class="card single-card"><h2>Detalle YTD por comercial</h2>
<input type="text" class="filter-input" id="t2Filter" placeholder="Filtrar...">
<div style="overflow-x:auto;"><table class="dt" id="t2Table">
<thead><tr><th>Comercial / Cliente</th><th style="text-align:right;">{range_label}</th><th style="text-align:right;">{cur_month_name}</th><th style="text-align:right;">YTD Actual</th><th style="text-align:right;">YTD Budget</th><th style="text-align:right;">YTD 2025</th><th style="text-align:right;">FY'26 Budget</th><th style="text-align:right;">FY'25</th><th style="text-align:right;">% FY'26</th></tr></thead>
<tbody>{t2_table_rows}</tbody></table></div></div>
<div class="tables-grid">
  <div class="card"><h2>Top 15 clientes YTD 2026</h2>
    <table class="dt"><thead><tr><th>Cliente</th><th style="text-align:right;">Count YTD</th></tr></thead><tbody>'''
    for cust, val in top_customers:
        html += f'<tr><td>{cust}</td><td class="r">{fmt(val)}</td></tr>'
    html += f'''</tbody></table></div>
  <div class="card"><h2>Status pedidos {cur_month_name} {CUR_YEAR}</h2>
    <table class="dt"><thead><tr><th>Status</th><th style="text-align:right;">Count</th></tr></thead><tbody>'''
    for s in status_order:
        v = agg['by_status_cur'].get(s, 0)
        html += f'<tr><td>{s}</td><td class="r">{fmt(v)}</td></tr>'
    html += f'''<tr class="row-grand"><td>Total {cur_month_name}</td><td class="r">{fmt(cur_month_total)}</td></tr></tbody></table></div>
</div>
<div class="footer">Dashboard generado a las {now} · Datos en vivo de Airtable (base Leaseir, tabla Pedidos)<br>Próxima actualización automática: mañana a las 8:00 AM (GitHub Actions)</div>
</div>
<script>
Chart.register(ChartDataLabels);
const COLORS={{navy:'#1F4E79',blue:'#305496',amber:'#f59e0b',green:'#10b981',red:'#ef4444',purple:'#8b5cf6',teal:'#14b8a6',gray:'#9ca3af'}};
function fmtN(v){{if(v===null||v===undefined)return '';if(Number.isInteger(v))return v;return v.toFixed(1)}}
new Chart(document.getElementById('evolutionChart'),{{type:'bar',data:{{labels:{json.dumps(MONTH_NAMES_FULL)},datasets:[
{{label:'Actual 2026',data:{json.dumps(actual_2026_monthly)},backgroundColor:COLORS.navy,borderRadius:4}},
{{label:'Budget 2026',data:{json.dumps(budget_2026)},backgroundColor:COLORS.amber,borderRadius:4}},
{{label:'Actual 2025',data:{json.dumps(fy25_actual)},backgroundColor:COLORS.gray,borderRadius:4}}
]}},options:{{responsive:true,plugins:{{legend:{{position:'top',labels:{{boxWidth:14,font:{{size:12}}}}}},datalabels:{{anchor:'end',align:'end',offset:2,font:{{size:9,weight:'bold'}},color:function(ctx){{return ctx.dataset.backgroundColor}},formatter:function(v){{return v>0?fmtN(v):''}}}}}},scales:{{y:{{beginAtZero:true,grid:{{color:'#f3f4f6'}},suggestedMax:95}},x:{{grid:{{display:false}}}}}}}}}});
new Chart(document.getElementById('cumChart'),{{type:'line',data:{{labels:{json.dumps(MONTH_NAMES_FULL)},datasets:[
{{label:'Actual 2026 (acum)',data:{json.dumps(actual_cum)},borderColor:COLORS.navy,fill:false,tension:0.25,borderWidth:3,pointRadius:5,pointBackgroundColor:COLORS.navy,spanGaps:false}},
{{label:'Budget 2026 (acum)',data:{json.dumps(budget_cum)},borderColor:COLORS.amber,borderDash:[6,4],fill:false,tension:0.25,borderWidth:2.5,pointRadius:4,pointBackgroundColor:COLORS.amber}},
{{label:'Actual 2025 (acum)',data:{json.dumps(fy25_cum)},borderColor:COLORS.gray,fill:false,tension:0.25,borderWidth:2,pointRadius:3,pointBackgroundColor:COLORS.gray}}
]}},options:{{responsive:true,plugins:{{legend:{{position:'top',labels:{{boxWidth:14,font:{{size:12}}}}}},datalabels:{{display:false}}}},scales:{{y:{{beginAtZero:true,grid:{{color:'#f3f4f6'}}}},x:{{grid:{{display:false}}}}}}}}}});
new Chart(document.getElementById('countriesChart'),{{type:'bar',data:{{labels:{json.dumps([c[0] for c in top_countries])},datasets:[{{label:'Count YTD',data:{json.dumps([c[1] for c in top_countries])},backgroundColor:COLORS.navy,borderRadius:4}}]}},options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}},datalabels:{{anchor:'end',align:'end',offset:4,font:{{size:11,weight:'bold'}},color:COLORS.navy,formatter:function(v){{return fmtN(v)}}}}}},scales:{{x:{{beginAtZero:true,grid:{{color:'#f3f4f6'}},suggestedMax:Math.max.apply(null,{json.dumps([c[1] for c in top_countries])})*1.15}},y:{{grid:{{display:false}}}}}}}}}});
new Chart(document.getElementById('commercialChart'),{{type:'doughnut',data:{{labels:{json.dumps(list(comm_ytd.keys()))},datasets:[{{data:{json.dumps(list(comm_ytd.values()))},backgroundColor:[COLORS.navy,COLORS.teal,COLORS.amber,COLORS.purple],borderWidth:2,borderColor:'#fff'}}]}},options:{{responsive:true,plugins:{{legend:{{position:'bottom',labels:{{boxWidth:12,font:{{size:11}}}}}},datalabels:{{color:'#fff',font:{{size:13,weight:'bold'}},formatter:function(v,ctx){{const t=ctx.dataset.data.reduce(function(a,b){{return a+b}},0);return fmtN(v)+'\\n('+Math.round(v/t*100)+'%)'}},textAlign:'center'}}}}}}}});
function setupFilter(i,t){{document.getElementById(i).addEventListener('input',function(e){{const q=e.target.value.toLowerCase();document.querySelectorAll('#'+t+' tbody tr').forEach(tr=>{{tr.style.display=(tr.dataset.label||'').includes(q)?'':'none'}})}})}}
setupFilter('t1Filter','t1Table');setupFilter('t2Filter','t2Table');
</script></body></html>'''
    return html

def main():
    pat = os.environ.get('AIRTABLE_PAT')
    if not pat:
        print("ERROR: AIRTABLE_PAT env var not set", file=sys.stderr)
        sys.exit(1)
    cur_month = int(os.environ.get('CUR_MONTH') or date.today().month)
    print(f"Fetching Pedidos from Airtable (current month={cur_month})...")
    records = fetch_pedidos(pat)
    print(f"  Got {len(records)} records")
    if not records:
        print("ERROR: 0 records — refusing to publish empty dashboard", file=sys.stderr)
        sys.exit(2)
    with open(BUDGETS_JSON) as f:
        bud = json.load(f)
    t1_bud = bud['t1']; t2_bud = bud['t2']
    agg = aggregate(records, cur_month)
    print(f"  T1 Total: range={agg['t1']['Total']['range']}, current={agg['t1']['Total']['current']}")
    html = build_html(agg, t1_bud, t2_bud, cur_month)
    out_path = OUTPUT_HTML
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ Wrote {out_path} ({len(html)} chars)")

if __name__ == '__main__':
    main()
