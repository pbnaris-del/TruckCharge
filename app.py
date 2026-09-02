from datetime import date
import urllib.parse
import streamlit as st
from util import (
    find_tier, find_band, format_thb, match_kiswire_customer,
    load_json, save_json, DATA_DIR, authenticate,
    fetch_month_from_ptt, ensure_fuel_price_auto,
    log_activity,
)

st.set_page_config(
    page_title="E-WAY Invoice Auditor",
    page_icon="🚛",
    layout="wide",
)

INJECTED_CSS = False


def inject_premium_css():
    global INJECTED_CSS
    if INJECTED_CSS:
        return
    INJECTED_CSS = True
    st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    :root {
        --font: 'Plus Jakarta Sans', sans-serif;
        --primary: #1a73e8;
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
        --card-bg: #ffffff;
        --card-border: #e2e8f0;
        --text-primary: #0f172a;
        --text-secondary: #64748b;
        --radius: 12px;
        --radius-sm: 8px;
    }

    .stApp { font-family: var(--font); }
    .main > div { animation: fadeIn 0.35s ease-out; }

    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #f8fafc;
        border-right: 1px solid var(--card-border);
    }

    .sidebar-section {
        margin-bottom: 1.25rem;
    }
    .sidebar-section-title {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-secondary);
        margin-bottom: 0.5rem;
        padding-bottom: 0.3rem;
        border-bottom: 1px solid var(--card-border);
    }
    .sidebar-section-title .sec-icon { margin-right: 0.35rem; }

    .price-source-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 0.6rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 2px 8px;
        border-radius: 4px;
        margin-left: 6px;
    }
    .price-source-badge.live { background: #d1fae5; color: #065f46; }
    .price-source-badge.json { background: #f1f5f9; color: #475569; }

    /* ── Hero ── */
    .hero-card {
        background: linear-gradient(135deg, #1a73e8 0%, #0d3b8f 100%);
        border-radius: var(--radius);
        padding: 1.5rem 2rem;
        margin-bottom: 1.5rem;
        color: white;
    }
    .hero-content { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; }
    .hero-left { display: flex; align-items: center; gap: 1rem; }
    .hero-icon {
        width: 44px; height: 44px;
        background: rgba(255,255,255,0.15);
        border-radius: 12px;
        display: flex;
        align-items: center; justify-content: center;
        font-size: 22px;
    }
    .hero-title { font-size: 1.35rem; font-weight: 800; line-height: 1.2; letter-spacing: -0.02em; }
    .hero-subtitle { font-size: 0.8rem; opacity: 0.7; font-weight: 400; margin-top: 1px; }
    .hero-right { display: flex; align-items: center; gap: 1rem; }
    .hero-date { text-align: right; font-size: 0.75rem; opacity: 0.8; line-height: 1.4; }
    .hero-date strong { font-size: 0.9rem; opacity: 1; }

    /* ── Verdict Banner ── */
    .verdict {
        border-radius: var(--radius);
        padding: 1.5rem 2rem;
        margin-bottom: 1.25rem;
        text-align: center;
    }
    .verdict.exact { background: linear-gradient(135deg, #d1fae5, #a7f3d0); color: #065f46; }
    .verdict.slight { background: linear-gradient(135deg, #fef3c7, #fde68a); color: #92400e; }
    .verdict.over { background: linear-gradient(135deg, #fee2e2, #fecaca); color: #991b1b; }
    .verdict.under { background: linear-gradient(135deg, #dbeafe, #bfdbfe); color: #1e40af; }
    .verdict-icon { font-size: 2rem; }
    .verdict-label { font-size: 1.4rem; font-weight: 800; letter-spacing: -0.01em; margin: 0.25rem 0 0.1rem; }
    .verdict-amount { font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; }
    .verdict-detail { font-size: 0.8rem; opacity: 0.75; margin-top: 0.3rem; }
    .verdict-detail span { display: inline-block; margin: 0 0.5rem; }

    /* ── Summary Strip ── */
    .summary-strip { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
    .summary-box {
        flex: 1;
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: var(--radius);
        padding: 1rem 1.25rem;
        text-align: center;
    }
    .summary-box .sb-label {
        font-size: 0.65rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--text-secondary);
        margin-bottom: 0.25rem;
    }
    .summary-box .sb-value {
        font-size: 1.35rem;
        font-weight: 800;
        color: var(--text-primary);
        letter-spacing: -0.01em;
    }
    .summary-box .sb-value.over { color: var(--danger); }
    .summary-box .sb-value.under { color: var(--success); }
    .summary-box .sb-value.zero { color: var(--text-primary); }

    /* ── Cards ── */
    .result-card {
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: var(--radius);
        padding: 1rem 1.25rem;
        height: 100%;
    }
    .result-card .rc-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid var(--card-border);
    }
    .result-card .rc-header h3 {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-secondary);
        margin: 0;
    }
    .result-card .rc-icon {
        width: 26px; height: 26px;
        border-radius: 6px;
        display: flex; align-items: center; justify-content: center;
        font-size: 13px;
        flex-shrink: 0;
    }
    .result-card .rc-icon.green { background: #d1fae5; }
    .result-card .rc-icon.blue { background: #dbeafe; }
    .result-card .rc-icon.amber { background: #fef3c7; }

    .rc-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.35rem 0;
        font-size: 0.8rem;
    }
    .rc-row + .rc-row { border-top: 1px solid #f1f5f9; }
    .rc-row .rc-label { color: var(--text-secondary); font-weight: 500; }
    .rc-row .rc-value { font-weight: 600; color: var(--text-primary); }
    .rc-row .rc-value.primary { color: var(--primary); }
    .rc-row .rc-value.success { color: var(--success); }
    .rc-row .rc-value.danger { color: var(--danger); }
    .rc-row .rc-value.warning { color: var(--warning); }

    .rc-divider { border: none; border-top: 1px dashed #e2e8f0; margin: 0.3rem 0; }

    .rc-na {
        text-align: center;
        color: var(--text-secondary);
        padding: 1.5rem 0.5rem;
        font-size: 0.8rem;
    }

    /* ── Misc ── */
    .stButton > button {
        font-family: var(--font) !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
    }
    .stExpander {
        border: 1px solid var(--card-border) !important;
        border-radius: var(--radius) !important;
        background: var(--card-bg) !important;
    }
    .stExpander summary { font-weight: 600 !important; font-size: 0.85rem !important; }
    section[data-testid="stSidebar"] hr { margin: 1rem 0; border-color: #e2e8f0; }
    div.stDataFrame { border: none !important; border-radius: var(--radius-sm) !important; overflow: hidden; }

    /* ── Prevent card data truncation without indication ── */
    .result-card .rc-row .rc-value { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    /* ── Wider dropdowns ── */
    section[data-testid="stSidebar"] { min-width: 340px; }
    .stSelectbox div[data-baseweb="select"] > div { white-space: normal !important; overflow: visible !important; }
    .stSelectbox div[data-baseweb="select"] span { white-space: normal !important; word-break: break-word; }

    @media print {
        section[data-testid="stSidebar"] { display: none !important; }
        .main .block-container { max-width: 100% !important; padding: 0 !important; }
        .hero-card { background: #1a73e8 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        .verdict { -webkit-print-color-adjust: exact; print-color-adjust: exact; break-inside: avoid; }
        .result-card { break-inside: avoid; }
        .stButton, button, .stSelectbox, .stDateInput, .stNumberInput, .stRadio { display: none !important; }
    }
</style>
""", unsafe_allow_html=True)


def load_all_data():
    baseline = load_json(DATA_DIR / "et_hq_baseline.json")
    kiswire = load_json(DATA_DIR / "kiswire_fsc.json")
    routes_cfg = load_json(DATA_DIR / "canonical_routes.json")
    et_routes = {r["id"]: r for r in routes_cfg["et_routes"]}
    fuel_prices = load_json(DATA_DIR / "ptt_fuel_prices.json")["prices"]
    master = load_json(DATA_DIR / "quotation_master.json")
    vendors = master["vendors"]
    kiswire_customers = load_json(DATA_DIR / "kiswire_customers_cost.json")
    return baseline, kiswire, et_routes, fuel_prices, vendors, kiswire_customers


def lookup_fuel_price(fuel_prices, d):
    return fuel_prices.get(d.isoformat())


def build_header_html(t, lang):
    today = date.today()
    date_str = today.strftime("%B %d, %Y")
    if lang == "TH":
        months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
                  "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
        date_str = f"{today.day} {months[today.month]} {today.year + 543}"
    return f"""
    <div class="hero-card">
        <div class="hero-content">
            <div class="hero-left">
                <div class="hero-icon">🚛</div>
                <div>
                    <div class="hero-title">{t['title']}</div>
                    <div class="hero-subtitle">{t['subtitle']}</div>
                </div>
            </div>
            <div class="hero-right">
                <div class="hero-date">
                    <strong>{date_str}</strong>
                </div>
            </div>
        </div>
    </div>
    """


def build_verdict_banner(variance, vendor_rate, bill, vendor_band, t):
    abs_var = abs(variance)
    if abs_var < 0.01:
        cls, icon, label = "exact", "✅", t["exact_match"]
    elif 0 < variance <= 50:
        cls, icon, label = "slight", "⚠️", t["over_slight"]
    elif variance > 50:
        cls, icon, label = "over", "❌", t["over_charged"]
    else:
        cls, icon, label = "under", "ℹ️", t["under_charged"]
    sign = "+" if variance >= 0 else ""
    return f"""
    <div class="verdict {cls}">
        <div class="verdict-icon">{icon}</div>
        <div class="verdict-label">{label}</div>
        <div class="verdict-amount">{sign}{format_thb(variance)} THB</div>
        <div class="verdict-detail">
            <span>{t["billed_amount"]}: {format_thb(bill)} THB</span>
            <span>·</span>
            <span>{t["quoted_rate"]}: {format_thb(vendor_rate)} THB</span>
            <span>·</span>
            <span>{t["band_used"]}: {vendor_band['min']:.2f}–{vendor_band['max']:.2f}</span>
        </div>
    </div>
    """


def build_summary_strip(vendor_rate, bill, variance, t):
    is_over = variance > 0
    is_under = variance < 0
    var_cls = "over" if is_over else "under" if is_under else "zero"
    sign = "+" if variance >= 0 else ""
    return f"""
    <div class="summary-strip">
        <div class="summary-box">
            <div class="sb-label">{t["quoted_rate"]}</div>
            <div class="sb-value">{format_thb(vendor_rate)}</div>
        </div>
        <div class="summary-box">
            <div class="sb-label">{t["billed_amount"]}</div>
            <div class="sb-value">{format_thb(bill)}</div>
        </div>
        <div class="summary-box">
            <div class="sb-label">{t["variance"]}</div>
            <div class="sb-value {var_cls}">{sign}{format_thb(variance)}</div>
        </div>
    </div>
    """


def build_result_card(icon_cls, icon_char, title, rows):
    r = ""
    for row in rows:
        if row.get("cls") == "divider":
            r += '<hr class="rc-divider">'
        else:
            cls = f" rc-value {row.get('cls', '')}"
            r += f'<div class="rc-row"><span class="rc-label">{row["label"]}</span><span class="{cls}">{row["value"]}</span></div>'
    return f"""
    <div class="result-card">
        <div class="rc-header">
            <div class="rc-icon {icon_cls}">{icon_char}</div>
            <h3>{title}</h3>
        </div>
        {r}
    </div>
    """


def build_na_card(msg):
    return f'<div class="result-card"><div class="rc-na">{msg}</div></div>'


def on_date_change():
    d = st.session_state.date_input
    price, _ = ensure_fuel_price_auto(d)
    if price is not None:
        st.session_state.diesel_input = price


def on_fetch_ptt_click():
    fetch_year = st.session_state.get("fetch_year", date.today().year + 543)
    fetch_month = st.session_state.get("fetch_month", 1)
    d = st.session_state.get("date_input", date.today())

    fp, added = fetch_month_from_ptt(int(fetch_year), int(fetch_month))
    if fp is None:
        st.session_state["_fetch_result"] = ("error", "PTT API returned no data for this month")
    else:
        st.session_state.pop("_fuel_prices_df", None)
        new_p = lookup_fuel_price(fp["prices"], d)
        if new_p is not None:
            st.session_state.diesel_input = new_p
        st.session_state["_fetch_result"] = ("success", f"✅ Fetched — {added} new entries added")


def main():
    inject_premium_css()

    # ── Login ──
    if "user" not in st.session_state:
        if st.session_state.get("_signed_out", False):
            st.session_state["_signed_out"] = False
            st.info("👋 Signed out successfully.")
        st.markdown("## 🚛 E-WAY Invoice Auditor")
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("### Sign In")
            username = st.text_input("Username", placeholder="admin", key="login_user")
            password = st.text_input("Password", type="password", placeholder="••••", key="login_pass")
            if st.button("Sign In", type="primary", use_container_width=True):
                u = authenticate(username, password)
                if u:
                    st.session_state["user"] = u
                    log_activity(u["username"], "login", f"Signed in as {u['display']} ({u['role']})")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        st.stop()

    user = st.session_state["user"]

    baseline, kiswire, et_routes, fuel_prices, vendors, kiswire_customers = load_all_data()
    customer_list = kiswire_customers["customers"]

    # ── Main: Top Bar ──
    tb1, tb2, tb3 = st.columns([1, 2, 1])
    with tb1:
        lang = st.selectbox("", ["EN", "TH"], index=0, label_visibility="collapsed")
    with tb2:
        st.markdown(
            f'<div style="text-align:center;font-size:0.8rem;font-weight:600;color:#0f172a;padding:0.25rem 0">'
            f'👤 {user["display"]} &nbsp;<span style="font-size:0.6rem;background:#e2e8f0;padding:1px 6px;border-radius:4px;color:#475569">{user["role"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with tb3:
        if st.button("🚪 Sign Out", use_container_width=True):
            log_activity(user["username"], "logout", f"User '{user['display']}' signed out")
            st.session_state["_signed_out"] = True
            for k in ["user", "diesel_input"]:
                st.session_state.pop(k, None)
            st.rerun()

    t = TRANS["TH"] if lang == "TH" else TRANS["EN"]

    # ── Sidebar: Selection ──
    st.sidebar.markdown(f'<div class="sidebar-section"><div class="sidebar-section-title"><span class="sec-icon">📋</span>{t["sel_section"]}</div></div>', unsafe_allow_html=True)

    vendor_names = sorted(vendors.keys())
    sel_vendor = st.sidebar.selectbox(t["vendor"], vendor_names, label_visibility="collapsed")
    vendor_data = vendors[sel_vendor]

    route_options = {r["display"]: r for r in vendor_data["routes"]}
    sel_route_display = st.sidebar.selectbox(t["route"], list(route_options.keys()), label_visibility="collapsed")
    sel_route = route_options[sel_route_display]

    gmap_q = sel_route_display.replace("→", " ").replace("->", " ").replace("-", " ")
    st.sidebar.markdown(
        f'<a href="https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(gmap_q)}" target="_blank" '
        f'style="font-size:0.75rem;color:#1a73e8;text-decoration:none;display:inline-flex;align-items:center;gap:4px;margin-top:-0.25rem;margin-bottom:0.6rem;font-weight:600;">'
        f'📍 Open route in Google Maps ↗</a>',
        unsafe_allow_html=True
    )

    container = st.sidebar.radio(t["container"], [t["both"], t["c20"], t["c40"]], horizontal=True, label_visibility="collapsed")
    is_40 = container == t["c40"]
    is_both = container == t["both"]

    # ── Sidebar: KISWIRE Customer ──
    st.sidebar.markdown(
        f'<div class="sidebar-section"><div class="sidebar-section-title">'
        f'<span class="sec-icon">📋</span>{t["kiswire_customer"]}</div></div>',
        unsafe_allow_html=True,
    )
    customer_indices = list(range(len(customer_list) + 1))
    def format_customer_opt(idx):
        if idx == 0:
            return t["select_kiswire"]
        c = customer_list[idx - 1]
        return f"{c['customer']} ({c['location']})"

    matched_idx = match_kiswire_customer(sel_route_display, sel_vendor, sel_route.get("et_route_id"), customer_list)
    default_idx = matched_idx + 1 if matched_idx is not None else 0
    sel_customer_idx = st.sidebar.selectbox(
        "",
        customer_indices,
        index=default_idx,
        format_func=format_customer_opt,
        label_visibility="collapsed"
    )
    sel_customer = customer_list[sel_customer_idx - 1] if sel_customer_idx > 0 else None
    sel_customer_name = sel_customer["customer"] if sel_customer else ""

    # ── Sidebar: Fuel Price ──
    st.sidebar.markdown(f'<div class="sidebar-section"><div class="sidebar-section-title"><span class="sec-icon">⛽</span>{t["fuel_section"]}</div></div>', unsafe_allow_html=True)

    today = date.today()
    if "diesel_input" not in st.session_state:
        price, _ = ensure_fuel_price_auto(today)
        st.session_state.diesel_input = price or 34.94

    d = st.sidebar.date_input(t["date"], value=today, key="date_input",
                              on_change=on_date_change, label_visibility="collapsed")

    diesel = st.sidebar.number_input(t["diesel"], min_value=0.0, max_value=99.99,
                                      key="diesel_input", step=0.01, format="%.2f", label_visibility="collapsed")

    json_ref = lookup_fuel_price(fuel_prices, d)
    fp_raw = load_json(DATA_DIR / "ptt_fuel_prices.json")
    is_actual = d.isoformat() in fp_raw.get("actual_dates", [])
    if json_ref is not None:
        badge_label = "OFFICIAL" if is_actual else "FORWARD-FILLED"
        badge_cls = "live" if is_actual else "json"
        st.sidebar.markdown(
            f'<div style="font-size:0.75rem;color:var(--text-secondary)">'
            f'PTT on {d.isoformat()}: <strong>{json_ref:.2f}</strong> THB/L'
            f'<span class="price-source-badge {badge_cls}">{badge_label}</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.warning(f"⚠️ No confirmed price for {d.isoformat()} — use 📡 Fetch or type manually")

    shown_price = st.session_state.diesel_input
    if user["role"] == "admin":
        col_a, col_b = st.sidebar.columns([1, 1])
        with col_a:
            if st.button("💾", key="btn_save_fuel", use_container_width=True):
                fp = load_json(DATA_DIR / "ptt_fuel_prices.json")
                fp["prices"][d.isoformat()] = shown_price
                save_json(DATA_DIR / "ptt_fuel_prices.json", fp)
                st.session_state.pop("_fuel_prices_df", None)
                st.success(f"✅ Saved {d.isoformat()} → {shown_price:.2f}")
                st.rerun()
        with col_b:
            if st.button("📡", key="btn_fetch_fuel", use_container_width=True):
                st.session_state._show_fuel_fetch = not st.session_state.get("_show_fuel_fetch", False)
        st.sidebar.caption("💾 Save  📡 Fetch")

    if st.session_state.get("_show_fuel_fetch", False):
        months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                     "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
        fetch_year = st.sidebar.number_input("Year (พ.ศ.)", value=date.today().year + 543,
                                             min_value=2560, max_value=2600, step=1, key="fetch_year")
        fetch_month = st.sidebar.selectbox("Month", list(range(1, 13)),
                                           format_func=lambda m: f"{m:02d} ({months_th[m-1]})",
                                           key="fetch_month")
        st.sidebar.button("📡 Fetch from PTT", type="primary", use_container_width=True,
                          on_click=on_fetch_ptt_click)

        if "_fetch_result" in st.session_state:
            res_type, res_msg = st.session_state.pop("_fetch_result")
            if res_type == "error":
                st.sidebar.error(res_msg)
            else:
                st.sidebar.success(res_msg)

    # ── Sidebar: Invoice ──
    st.sidebar.markdown(f'<div class="sidebar-section"><div class="sidebar-section-title"><span class="sec-icon">🧾</span>{t["inv_section"]}</div></div>', unsafe_allow_html=True)

    billed = st.sidebar.number_input(t["billed"], min_value=0.0, max_value=999999.0,
                                      value=0.0, step=100.0, format="%.2f", label_visibility="collapsed")

    st.sidebar.markdown("---")
    validate = st.sidebar.button(t["validate"], type="primary", use_container_width=True)

    # ── Main: Hero ──
    st.markdown(build_header_html(t, lang), unsafe_allow_html=True)

    # ── Price Tiers Reference ──
    with st.container(border=True):
        bands = sel_route["bands"]
        live_band = find_band(bands, diesel)

        # Row 1: Vendor / Route / Active band
        ccols = st.columns([1, 1, 3])
        with ccols[0]:
            st.caption(f"**{sel_vendor}**")
        with ccols[1]:
            st.caption(f"**{sel_route_display}**")
        with ccols[2]:
            if live_band:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">'
                    f'<span style="font-size:0.65rem;font-weight:600;color:#64748b">Active:</span>'
                    f'<span style="display:inline-block;background:#1a73e8;color:white;padding:1px 10px;border-radius:4px;font-size:0.75rem;font-weight:600">'
                    f'{live_band["min"]:.1f}–{live_band["max"]:.1f} → {live_band["rate"]:.0f} THB</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("No band matches current diesel price")

        # Row 2: All bands in expander (auto-open if no match or few bands)
        n = len(bands)
        expanded_default = n <= 5 or not live_band
        with st.expander(f"All {n} bands", expanded=expanded_default):
            bands_html = "".join(
                f'<span style="display:inline-block;background:#f1f5f9;padding:1px 8px;margin:1px 2px;border-radius:4px;font-size:0.7rem;white-space:nowrap">'
                f'{b["min"]:.1f}–{b["max"]:.1f} → {b["rate"]:.0f} THB</span>'
                for b in bands
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:4px;flex-wrap:wrap">{bands_html}</div>',
                unsafe_allow_html=True,
            )

    if not validate:
        st.info(t["prompt"])
        return

    # ── Computation ──
    bands = sel_route["bands"]
    vendor_band = find_band(bands, diesel)
    if vendor_band is None:
        bands_range = f"{bands[0]['min']:.2f}–{bands[-1]['max']:.2f} THB/L"
        st.error(f"{t['no_band_vendor'].format(diesel)}\n\n{t['available_range']}: {bands_range}")
        st.stop()
    vendor_rate = vendor_band["rate"]
    variance = billed - vendor_rate
    is_over = variance > 0
    is_under = variance < 0

    is_et = sel_route.get("is_et_route", False) and sel_route.get("et_route_id") in et_routes
    hq_data = None
    if is_et:
        et_id = sel_route["et_route_id"]
        route_base = baseline["routes"].get(et_id)
        if route_base:
            base_rate = route_base["base_rate"]
            fsc_tier = find_tier(baseline["fsc_tiers"], diesel)
            fsc_amount = fsc_tier["surcharge"] if fsc_tier else 0
            hq_total = base_rate + fsc_amount
            margin = hq_total - vendor_rate
            hq_data = dict(base_rate=base_rate, fsc_tier=fsc_tier, fsc_amount=fsc_amount,
                           hq_total=hq_total, margin=margin)

    k_tier = find_tier(kiswire["fsc_tiers"], diesel)
    k_markup = k_tier["markup_usd"] if k_tier else 0

    # ── Verdict Banner ──
    st.markdown(build_verdict_banner(variance, vendor_rate, billed, vendor_band, t), unsafe_allow_html=True)

    # ── Summary Numbers ──
    st.markdown(build_summary_strip(vendor_rate, billed, variance, t), unsafe_allow_html=True)

    # ── Detail Cards ──
    c1, c2, c3 = st.columns(3)

    with c1:
        rows = [
            {"label": t["quoted_rate"], "value": f"{format_thb(vendor_rate)} THB"},
            {"label": t["billed_amount"], "value": f"{format_thb(billed)} THB"},
            {"label": "", "value": "", "cls": "divider"},
            {"label": t["variance"], "value": f"{'+' if variance >= 0 else ''}{format_thb(variance)} THB",
             "cls": "danger" if is_over else "success" if is_under else ""},
            {"label": "", "value": "", "cls": "divider"},
            {"label": t["band_used"], "value": f"{vendor_band['min']:.2f}–{vendor_band['max']:.2f}"},
        ]
        st.markdown(build_result_card("green", "💰", t["costing"], rows), unsafe_allow_html=True)

    with c2:
        if hq_data:
            d = hq_data
            margin_cls = "success" if d["margin"] >= 0 else "danger"
            margin_label = t["profit"] if d["margin"] >= 0 else t["loss"]
            rows = [
                {"label": t["base"], "value": f"{format_thb(d['base_rate'])} THB"},
                {"label": t["fsc"], "value": f"+ {format_thb(d['fsc_amount'])} THB",
                 "cls": "warning"},
                {"label": "", "value": "", "cls": "divider"},
                {"label": t["total"], "value": f"{format_thb(d['hq_total'])} THB", "cls": "primary"},
                {"label": "", "value": "", "cls": "divider"},
                {"label": t["margin_vs_cost"], "value": f"{format_thb(d['margin'])} THB ({margin_label})",
                 "cls": margin_cls},
            ]
            st.markdown(build_result_card("blue", "🏢", t["pricing_hq_title"], rows), unsafe_allow_html=True)
        else:
            st.markdown(build_na_card(t["not_et_route"]), unsafe_allow_html=True)

    with c3:
        if sel_customer is None:
            st.markdown(build_na_card("Select a KISWIRE customer to see 20' & 40' cost breakdown"), unsafe_allow_html=True)
        else:
            cost_20 = sel_customer.get("trucking_20_usd")
            cost_40 = sel_customer.get("trucking_40_usd")
            fsc_20 = k_markup if k_tier else 0
            fsc_40 = (k_markup * 2) if k_tier else 0
            total_20 = (cost_20 + fsc_20) if cost_20 is not None else None
            total_40 = (cost_40 + fsc_40) if cost_40 is not None else None

            rows = [
                {"label": sel_customer_name[:32], "value": f"{sel_customer['location'][:20]}"},
                {"label": "Port", "value": f"{sel_customer['port'][:20]}"},
                {"label": "", "value": "", "cls": "divider"},
                {"label": "📦 20' Total Est.", "value": f"$ {total_20:.0f} USD" if total_20 else "N/A", "cls": "primary" if not is_40 else ""},
                {"label": "  ├ 20' Base", "value": f"$ {cost_20:.0f} USD" if cost_20 else "N/A"},
                {"label": "  └ 20' FSC (1×)", "value": f"+ $ {fsc_20:.0f} USD" if k_tier else "$ 0 USD", "cls": "warning"},
                {"label": "", "value": "", "cls": "divider"},
                {"label": "📦 40' Total Est.", "value": f"$ {total_40:.0f} USD" if total_40 else "N/A", "cls": "primary" if is_40 or is_both else ""},
                {"label": "  ├ 40' Base", "value": f"$ {cost_40:.0f} USD" if cost_40 else "N/A"},
                {"label": "  └ 40' FSC (2×)", "value": f"+ $ {fsc_40:.0f} USD" if k_tier else "$ 0 USD", "cls": "warning"},
            ]
            st.markdown(build_result_card("amber", "📋", t["kiswire_title"], rows), unsafe_allow_html=True)

    # ── Combined 20' & 40' Container Matrix Section ──
    st.markdown(f'<div style="margin-top:1.5rem;margin-bottom:0.75rem;display:flex;align-items:center;gap:8px;"><span style="font-size:1.1rem;">📦</span><h3 style="font-size:0.95rem;font-weight:700;margin:0;color:var(--text-primary);">{t["dual_title"]}</h3></div>', unsafe_allow_html=True)

    col_20, col_40 = st.columns(2)
    with col_20:
        cost_20_val = sel_customer.get("trucking_20_usd") if sel_customer else None
        fsc_20_val = k_markup if k_tier else 0
        tot_20_val = (cost_20_val + fsc_20_val) if cost_20_val is not None else None
        tot_20_thb = (tot_20_val * 35.0) if tot_20_val else None

        rows_20 = [
            {"label": "Equipment Profile", "value": "20' Container / Standard Dry", "cls": "primary"},
            {"label": t["quoted_rate"], "value": f"{format_thb(vendor_rate)} THB"},
            {"label": t["billed_amount"], "value": f"{format_thb(billed)} THB" if (not is_40 and billed > 0) else "—"},
            {"label": "", "value": "", "cls": "divider"},
            {"label": "KISWIRE Base Cost", "value": f"$ {cost_20_val:.0f} USD" if cost_20_val else "N/A"},
            {"label": "KISWIRE FSC Markup (1×)", "value": f"+ $ {fsc_20_val:.0f} USD", "cls": "warning"},
            {"label": "KISWIRE Total Customer Cost", "value": f"$ {tot_20_val:.0f} USD" if tot_20_val else "N/A", "cls": "primary"},
            {"label": "Est. THB Eqv (@35 THB/USD)", "value": f"~{format_thb(tot_20_thb)} THB" if tot_20_thb else "N/A"},
        ]
        badge_20 = " <span style='font-size:0.65rem;background:#dbeafe;color:#1e40af;padding:2px 6px;border-radius:4px;'>Selected</span>" if not is_40 and not is_both else ""
        st.markdown(build_result_card("blue", "📦", f"20' Container Profile{badge_20}", rows_20), unsafe_allow_html=True)

    with col_40:
        cost_40_val = sel_customer.get("trucking_40_usd") if sel_customer else None
        fsc_40_val = (k_markup * 2) if k_tier else 0
        tot_40_val = (cost_40_val + fsc_40_val) if cost_40_val is not None else None
        tot_40_thb = (tot_40_val * 35.0) if tot_40_val else None

        rows_40 = [
            {"label": "Equipment Profile", "value": "40' Container / High Cube", "cls": "primary"},
            {"label": t["quoted_rate"], "value": f"{format_thb(vendor_rate)} THB"},
            {"label": t["billed_amount"], "value": f"{format_thb(billed)} THB" if (is_40 and billed > 0) else "—"},
            {"label": "", "value": "", "cls": "divider"},
            {"label": "KISWIRE Base Cost", "value": f"$ {cost_40_val:.0f} USD" if cost_40_val else "N/A"},
            {"label": "KISWIRE FSC Markup (2×)", "value": f"+ $ {fsc_40_val:.0f} USD", "cls": "warning"},
            {"label": "KISWIRE Total Customer Cost", "value": f"$ {tot_40_val:.0f} USD" if tot_40_val else "N/A", "cls": "primary"},
            {"label": "Est. THB Eqv (@35 THB/USD)", "value": f"~{format_thb(tot_40_thb)} THB" if tot_40_thb else "N/A"},
        ]
        badge_40 = " <span style='font-size:0.65rem;background:#dbeafe;color:#1e40af;padding:2px 6px;border-radius:4px;'>Selected</span>" if is_40 else ""
        st.markdown(build_result_card("green", "📦", f"40' Container Profile{badge_40}", rows_40), unsafe_allow_html=True)


TRANS = {
    "EN": {
        "vendor": "Vendor",
        "route": "Route",
        "container": "Container Size",
        "c20": "20'",
        "c40": "40'",
        "both": "Both 20' & 40'",
        "date": "Service Date",
        "diesel": "Diesel Price",
        "billed": "Billed Amount (THB)",
        "validate": "Validate Invoice",
        "title": "E-WAY Invoice Auditor",
        "subtitle": "Validate trucking charges against quotations & 20'/40' container benchmarks",
        "prompt": "Fill in the sidebar and click **Validate Invoice**.",
        "no_band_vendor": "No matching price band for diesel {:.2f} THB/L.",
        "base": "Base Rate",
        "fsc": "FSC",
        "total": "Total",
        "margin_vs_cost": "Margin vs Cost",
        "profit": "Profit",
        "loss": "Loss",
        "fsc_tier_label": "FSC Tier",
        "container_adjust": "Container Adj.",
        "kiswire_40_note": "40' container: 2× standard FSC markup",
        "kiswire_20_note": "20' container: standard FSC markup",
        "costing": "Costing",
        "quoted_rate": "Quoted Rate",
        "billed_amount": "Billed",
        "variance": "Variance",
        "band_used": "Band",
        "pricing_hq_title": "HQ Pricing",
        "kiswire_title": "KISWIRE FSC (20' & 40')",
        "kiswire_customer": "KISWIRE Customer",
        "select_kiswire": "— Select KISWIRE customer —",
        "available_range": "Available diesel range",
        "not_et_route": "Not an ET route. HQ pricing not available.",
        "exact_match": "Exact Match",
        "over_slight": "Slightly Overcharged",
        "over_charged": "Overcharged",
        "under_charged": "Undercharged",
        "sel_section": "Selection",
        "fuel_section": "Fuel Price",
        "save_fuel": "Save",
        "save_range": "Range",
        "inv_section": "Invoice",
        "dual_title": "Combined Container Analysis (20' vs 40')",
    },
    "TH": {
        "vendor": "ผู้ให้บริการ",
        "route": "เส้นทาง",
        "container": "ประเภทตู้",
        "c20": "20'",
        "c40": "40'",
        "both": "ทั้ง 20' และ 40'",
        "date": "วันที่ให้บริการ",
        "diesel": "ราคาดีเซล",
        "billed": "จำนวนเงิน (บาท)",
        "validate": "ตรวจสอบใบแจ้งหนี้",
        "title": "E-WAY ตรวจสอบใบแจ้งหนี้ค่ารถ",
        "subtitle": "ตรวจสอบค่าใช้จ่ายขนส่งเทียบกับใบเสนอราคาและราคาเปรียบเทียบทั้งตู้ 20' และ 40'",
        "prompt": "กรอกข้อมูลในแถบด้านข้างแล้วคลิก **ตรวจสอบใบแจ้งหนี้**",
        "no_band_vendor": "ไม่มีช่วงราคาที่ตรงกับดีเซล {:.2f} บาท/ลิตร",
        "base": "ราคาฐาน",
        "fsc": "ส่วนปรับน้ำมัน",
        "total": "รวม",
        "margin_vs_cost": "กำไร/ขาดทุน",
        "profit": "กำไร",
        "loss": "ขาดทุน",
        "fsc_tier_label": "ช่วง FSC",
        "container_adjust": "ปรับตามตู้",
        "kiswire_40_note": "ตู้ 40' : 2 เท่าของ FSC",
        "kiswire_20_note": "ตู้ 20' : FSC มาตรฐาน",
        "costing": "ต้นทุน",
        "quoted_rate": "ราคาเสนอ",
        "billed_amount": "ใบแจ้งหนี้",
        "variance": "ส่วนต่าง",
        "band_used": "ช่วงดีเซล",
        "pricing_hq_title": "ราคาขาย (HQ)",
        "kiswire_title": "KISWIRE FSC (ตู้ 20' & 40')",
        "kiswire_customer": "ลูกค้า KISWIRE",
        "select_kiswire": "— เลือกลูกค้า KISWIRE —",
        "available_range": "ช่วงดีเซลที่มี",
        "not_et_route": "ไม่ใช่เส้นทาง ET ไม่มีข้อมูลราคา HQ",
        "exact_match": "ตรงกันพอดี",
        "over_slight": "สูงกว่าเล็กน้อย",
        "over_charged": "เรียกเก็บเกิน",
        "under_charged": "เรียกเก็บต่ำกว่า",
        "sel_section": "การเลือก",
        "fuel_section": "ราคาน้ำมัน",
        "save_fuel": "บันทึก",
        "save_range": "ช่วงวันที่",
        "inv_section": "ใบแจ้งหนี้",
        "dual_title": "การเปรียบเทียบตู้ 20' และ 40' ร่วมกัน",
    },
}

if __name__ == "__main__":
    main()

