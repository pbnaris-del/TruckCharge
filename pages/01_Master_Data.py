import streamlit as st
import pandas as pd
from util import (
    load_json, save_json, DATA_DIR, authenticate,
    _load_master, _save_vendor_to_master,
    _delete_vendor_from_master, _save_route_to_master,
    _delete_route_from_master, _save_bands_to_master,
    get_activity_log, fetch_month_from_ptt,
    parse_rate_sheet_file,
)

st.set_page_config(page_title="Master Data Management", page_icon="🛠️", layout="wide")

# ── Login ──
if "user" not in st.session_state:
    st.markdown("## 🛠️ Master Data Management")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Sign In")
        u_name = st.text_input("Username", placeholder="admin", key="md_login_user")
        u_pass = st.text_input("Password", type="password", placeholder="••••", key="md_login_pass")
        if st.button("Sign In", type="primary", use_container_width=True):
            u = authenticate(u_name, u_pass)
            if u:
                st.session_state["user"] = u
                st.rerun()
            else:
                st.error("Invalid username or password")
    st.stop()

user = st.session_state["user"]
username = user["username"]

# ── Stored messages (survive rerun) ──
if "_admin_msg" in st.session_state:
    msg, kind = st.session_state.pop("_admin_msg")
    if kind == "success":
        st.success(msg)
    elif kind == "warning":
        st.warning(msg)
    elif kind == "error":
        st.error(msg)
    elif kind == "info":
        st.info(msg)

# ── User bar ──
st.markdown(
    f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.5rem">'
    f'<span style="font-size:0.8rem;font-weight:600">👤 {user["display"]} | <span style="font-size:0.65rem;background:#e2e8f0;padding:1px 6px;border-radius:4px;color:#475569">{user["role"]}</span></span>'
    f'</div>',
    unsafe_allow_html=True,
)

ac1, ac2 = st.columns([5, 1])
with ac1:
    st.title("🛠️ Master Data Management")
    st.caption("Add, edit, and delete vendors, routes, and price tiers.")
with ac2:
    if st.button("🚪 Sign Out", use_container_width=True):
        st.session_state["_signed_out"] = True
        for k in ["user"]:
            st.session_state.pop(k, None)
        st.rerun()

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    .stApp { font-family: 'Plus Jakarta Sans', sans-serif; }
    .block-container { padding-top: 1.5rem; }
    .stButton > button { font-family: 'Plus Jakarta Sans', sans-serif !important; font-weight: 600 !important; border-radius: 8px !important; }
    div.stDataFrame { border: none !important; border-radius: 8px !important; overflow: hidden; }
    h1, h2, h3 { font-weight: 700; letter-spacing: -0.02em; }
    hr { margin: 1rem 0; border-color: #e2e8f0; }
</style>
""", unsafe_allow_html=True)

routes_cfg = load_json(DATA_DIR / "canonical_routes.json")
et_routes = {r["id"]: r for r in routes_cfg["et_routes"]}
master = _load_master()
vendors = master["vendors"]

vendor_names = sorted(vendors.keys())

# ── SECTION: VENDOR ──
st.header("Vendors")
with st.container(border=True):
    cv1, cv2 = st.columns([2, 3])
    with cv1:
        sel_vendor = st.selectbox("Select Vendor", vendor_names, key="admin_sel_vendor")
        vendor_data = vendors[sel_vendor]
    with cv2:
        with st.popover("➕ Add Vendor", use_container_width=True):
            new_v = st.text_input("Vendor name", key="av_name", placeholder="e.g. NEWCO")
            if st.button("Add", key="btn_av", type="primary", use_container_width=True):
                if not new_v.strip():
                    st.warning("Enter a name.")
                elif new_v.strip() in vendors:
                    st.warning(f"'{new_v.strip()}' exists.")
                else:
                    _save_vendor_to_master(new_v.strip(), {"company": new_v.strip(), "notes": "", "routes": []}, username=username)
                    st.session_state["_admin_msg"] = (f"✅ Vendor '{new_v.strip()}' added", "success")
                    st.rerun()

    with st.container(border=True):
        st.markdown("**Edit Vendor**")
        v_company = st.text_input("Company", value=vendor_data.get("company", ""), key=f"av_company_{sel_vendor}")
        v_notes = st.text_area("Notes", value=vendor_data.get("notes", ""), key=f"av_notes_{sel_vendor}", height=60)
        ec1, ec2 = st.columns([1, 1])
        with ec1:
            if st.button("💾 Save Vendor", key="btn_save_v", type="primary", use_container_width=True):
                fresh = _load_master()["vendors"][sel_vendor]["routes"]
                _save_vendor_to_master(sel_vendor, {"company": v_company, "notes": v_notes, "routes": fresh}, username=username)
                st.session_state["_admin_msg"] = (f"✅ Vendor '{sel_vendor}' updated", "success")
                st.rerun()
        with ec2:
            if st.button("🗑 Delete Vendor", key="btn_del_v", use_container_width=True):
                st.session_state.confirm_del_v = True
            if st.session_state.get("confirm_del_v"):
                st.error(f"Delete vendor '{sel_vendor}' and all its routes?")
                db1, db2 = st.columns(2)
                with db1:
                    if st.button("Yes, delete", key="btn_del_v_yes", type="primary"):
                        _delete_vendor_from_master(sel_vendor, username=username)
                        st.session_state.confirm_del_v = False
                        st.session_state["_admin_msg"] = (f"🗑 Vendor '{sel_vendor}' deleted", "success")
                        st.rerun()
                with db2:
                    if st.button("Cancel", key="btn_del_v_no"):
                        st.session_state.confirm_del_v = False
                        st.rerun()

# ── SECTION: ROUTE ──
st.header("Routes")
with st.container(border=True):
    route_options = {r["display"]: r for r in vendors[sel_vendor]["routes"]}
    route_displays = list(route_options.keys())

    rr1, rr2 = st.columns([2, 3])
    with rr1:
        if route_displays:
            sel_route_display = st.selectbox("Select Route", route_displays, key="admin_sel_route")
            sel_route = route_options[sel_route_display]
        else:
            st.info("No routes for this vendor.")
            sel_route = None
            sel_route_display = None
    with rr2:
        with st.popover("➕ Add Route", use_container_width=True):
            new_r = st.text_input("Display name", key="ar_name", placeholder="e.g. BKK → GWS LCB")
            ar_et = st.checkbox("ET route", key="ar_et")
            ar_et_id = ""
            if ar_et:
                ar_et_id = st.selectbox("ET ID", sorted(et_routes.keys()), key="ar_et_id")
            if st.button("Add", key="btn_ar", type="primary", use_container_width=True):
                if not new_r.strip():
                    st.warning("Enter a route name.")
                else:
                    rid = new_r.strip().lower().replace(" ", "_").replace("→", "to")
                    rid = "".join(c if c.isalnum() or c == "_" else "_" for c in rid)
                    route = {"id": rid, "display": new_r.strip(), "is_et_route": ar_et, "bands": [{"min": 0, "max": 99.99, "rate": 0}]}
                    if ar_et:
                        route["et_route_id"] = ar_et_id
                    _save_route_to_master(sel_vendor, route, append=True, username=username)
                    st.session_state["_admin_msg"] = (f"✅ Route '{new_r.strip()}' added to {sel_vendor}", "success")
                    st.rerun()

    if sel_route is not None:
        with st.container(border=True):
            st.markdown("**Edit Route**")
            _rk = f"{sel_vendor}::{sel_route_display}"
            r_name = st.text_input("Display name", value=sel_route_display, key=f"ar_name_{_rk}")
            r_et = st.checkbox("ET route", value=sel_route.get("is_et_route", False), key=f"ar_et_{_rk}")
            r_et_id = sel_route.get("et_route_id", "")
            if r_et:
                r_et_id = st.selectbox("ET ID", sorted(et_routes.keys()),
                                        index=sorted(et_routes.keys()).index(r_et_id) if r_et_id in et_routes else 0,
                                        key=f"ar_et_id_{_rk}")
            ec1, ec2 = st.columns([1, 1])
            with ec1:
                if st.button("💾 Save Route", key="btn_save_r", type="primary", use_container_width=True):
                    rid = r_name.strip().lower().replace(" ", "_").replace("→", "to")
                    rid = "".join(c if c.isalnum() or c == "_" else "_" for c in rid)
                    route = {"id": rid, "display": r_name.strip(), "is_et_route": r_et, "bands": sel_route["bands"]}
                    if r_et:
                        route["et_route_id"] = r_et_id
                    else:
                        route.pop("et_route_id", None)
                    _save_route_to_master(sel_vendor, route, append=False, old_display=sel_route_display, username=username)
                    st.session_state["_admin_msg"] = ("✅ Route updated", "success")
                    st.rerun()
            with ec2:
                if st.button("🗑 Delete Route", key="btn_del_r", use_container_width=True):
                    st.session_state.confirm_del_r = True
                if st.session_state.get("confirm_del_r"):
                    st.error(f"Delete route '{sel_route_display}'?")
                    db1, db2 = st.columns(2)
                    with db1:
                        if st.button("Yes, delete", key="btn_del_r_yes", type="primary"):
                            _delete_route_from_master(sel_vendor, sel_route_display, username=username)
                            st.session_state.confirm_del_r = False
                            st.session_state["_admin_msg"] = ("🗑 Route deleted", "success")
                            st.rerun()
                    with db2:
                        if st.button("Cancel", key="btn_del_r_no"):
                            st.session_state.confirm_del_r = False
                            st.rerun()

# ── SECTION: PRICE TIERS ──
# Track last vendor+route combo for bands cache busting
if sel_route is not None:
    _bands_combo = f"{sel_vendor}::{sel_route_display}"
    if st.session_state.get("_last_bands_combo") != _bands_combo:
        for k in list(st.session_state.keys()):
            if k.startswith("master_bands_"):
                del st.session_state[k]
        st.session_state["_last_bands_combo"] = _bands_combo

if sel_route is not None:
    st.header("Price Tiers")
    st.caption(f"Editing bands for **{sel_vendor} → {sel_route_display}**")

    bands_key = f"master_bands_{sel_vendor}::{sel_route_display}"
    if bands_key not in st.session_state:
        st.session_state[bands_key] = pd.DataFrame(sel_route["bands"])

    edited = st.data_editor(
        st.session_state[bands_key],
        column_config={
            "min": st.column_config.NumberColumn("Min (THB/L)", format="%.2f"),
            "max": st.column_config.NumberColumn("Max (THB/L)", format="%.2f"),
            "rate": st.column_config.NumberColumn("Rate (THB)", format="%.2f"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
    )
    if edited is not None:
        st.session_state[bands_key] = edited if isinstance(edited, pd.DataFrame) else pd.DataFrame(edited)

    if st.button("💾 Save All Changes to Master File", key="btn_save_master", type="primary", use_container_width=True):
        df = st.session_state[bands_key]
        edited_bands = df.to_dict("records") if isinstance(df, pd.DataFrame) else list(df)
        _save_bands_to_master(sel_vendor, sel_route_display, edited_bands, username=username)
        st.session_state["_admin_msg"] = ("✅ All changes saved to master file", "success")
        st.rerun()

# ── SECTION: IMPORT RATE SHEET ──
st.header("📥 Import Rate Sheet (PDF / Excel)")
st.caption("Upload vendor rate sheets in Excel (.xlsx, .xls, .csv) or PDF (.pdf) format to parse, edit, and import price tiers into Master Data.")
with st.container(border=True):
    uploaded_file = st.file_uploader(
        "Choose a Rate Sheet file",
        type=["xlsx", "xls", "csv", "pdf"],
        key="rate_sheet_file_uploader",
        help="Upload PDF or Excel files containing fuel price tiers and freight rates."
    )
    if uploaded_file is not None:
        with st.spinner("Parsing rate sheet..."):
            extracted_records = parse_rate_sheet_file(uploaded_file, uploaded_file.name)

        if not extracted_records:
            st.warning("⚠️ No valid rate tiers or price bands could be automatically extracted from this file. Please verify the file contents or column formatting.")
        else:
            st.success(f"✅ Successfully extracted **{len(extracted_records)}** rate tier entries from **{uploaded_file.name}**!")

            ext_df = pd.DataFrame(extracted_records)
            st.markdown("##### ✏️ Edit & Fix Extracted Data")
            st.caption("You can edit any values below (Route, Min, Max, Rate) to fix errors before importing.")
            edited_ext_df = st.data_editor(
                ext_df,
                column_config={
                    "route_display": st.column_config.TextColumn("Route / Destination"),
                    "min": st.column_config.NumberColumn("Min (THB/L)", format="%.2f"),
                    "max": st.column_config.NumberColumn("Max (THB/L)", format="%.2f"),
                    "rate": st.column_config.NumberColumn("Rate (THB)", format="%.2f"),
                },
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                key="ext_rates_editor"
            )

            st.markdown("##### 🎯 Select Target Vendor & Route for Update")
            ic1, ic2 = st.columns([1, 1])
            with ic1:
                vendor_opts = ["➕ Create New Vendor..."] + vendor_names
                sel_imp_vendor_opt = st.selectbox("Target Vendor", vendor_opts, key="import_target_vendor")
                if sel_imp_vendor_opt == "➕ Create New Vendor...":
                    target_vendor = st.text_input("New Vendor Name", key="imp_new_v_name", placeholder="e.g. NEWCO").strip().upper()
                else:
                    target_vendor = sel_imp_vendor_opt

            with ic2:
                existing_routes = [r["display"] for r in vendors[target_vendor]["routes"]] if target_vendor in vendors else []
                route_opts = ["➕ Create New Route..."] + existing_routes
                sel_imp_route_opt = st.selectbox("Target Route", route_opts, key="import_target_route")
                if sel_imp_route_opt == "➕ Create New Route...":
                    target_route = st.text_input("New Route Name", key="imp_new_r_name", placeholder="e.g. BKK → LCB").strip()
                else:
                    target_route = sel_imp_route_opt

            if st.button("📥 Apply & Save Imported Tiers to Master Data", type="primary", use_container_width=True):
                if not target_vendor:
                    st.error("Please select or enter a Target Vendor.")
                elif not target_route:
                    st.error("Please select or enter a Target Route.")
                else:
                    if target_vendor not in vendors:
                        _save_vendor_to_master(target_vendor, {"company": target_vendor, "notes": "", "routes": []}, username=username)

                    master_latest = _load_master()
                    v_routes = master_latest["vendors"].get(target_vendor, {}).get("routes", [])
                    r_exists = any(r["display"] == target_route for r in v_routes)

                    bands_to_save = []
                    for r in edited_ext_df.to_dict("records"):
                        if pd.notna(r.get("min")) and pd.notna(r.get("max")) and pd.notna(r.get("rate")):
                            bands_to_save.append({
                                "min": float(r["min"]),
                                "max": float(r["max"]),
                                "rate": float(r["rate"])
                            })

                    if not bands_to_save:
                        st.error("No valid price tiers to save.")
                    else:
                        if not r_exists:
                            rid = target_route.lower().replace(" ", "_").replace("→", "to")
                            rid = "".join(c if c.isalnum() or c == "_" else "_" for c in rid)
                            new_route_obj = {"id": rid, "display": target_route, "is_et_route": False, "bands": bands_to_save}
                            _save_route_to_master(target_vendor, new_route_obj, append=True, username=username)
                        else:
                            _save_bands_to_master(target_vendor, target_route, bands_to_save, username=username)

                        st.session_state.pop(f"master_bands_{target_vendor}::{target_route}", None)
                        st.session_state["_admin_msg"] = (f"✅ Imported {len(bands_to_save)} rate tiers into Vendor '{target_vendor}' → Route '{target_route}'", "success")
                        st.rerun()

# ── SECTION: FUEL PRICES ──
st.header("⛽ Fuel Prices")
st.caption("Manage PTT diesel price history. Add/edit prices for any date — past or future.")
with st.container(border=True):
    fp = load_json(DATA_DIR / "ptt_fuel_prices.json")
    prices = fp["prices"]
    fp_key = "_fuel_prices_df"
    if fp_key not in st.session_state:
        df = pd.DataFrame(sorted(prices.items(), key=lambda x: x[0]), columns=["Date", "Price (THB/L)"])
        df["Date"] = pd.to_datetime(df["Date"])
        st.session_state[fp_key] = df

    full_df = st.session_state[fp_key].copy()

    from datetime import date as dt_date
    years = sorted(list({d.year for d in full_df["Date"] if pd.notna(d)}), reverse=True)
    curr_year = dt_date.today().year
    default_year_idx = years.index(curr_year) + 1 if curr_year in years else (1 if years else 0)

    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                 "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

    cf1, cf2, cf3 = st.columns([1, 1, 2])
    with cf1:
        sel_year = st.selectbox(
            "Filter Year",
            ["All Years"] + [str(y) for y in years],
            index=default_year_idx if len(years) > 0 else 0,
            key="fp_filter_year"
        )
    with cf2:
        curr_month = dt_date.today().month
        sel_month = st.selectbox(
            "Filter Month",
            ["All Months"] + [f"{m:02d} ({months_th[m-1]})" for m in range(1, 13)],
            index=curr_month if sel_year != "All Years" else 0,
            key="fp_filter_month"
        )
    with cf3:
        st.markdown("<br>", unsafe_allow_html=True)

    # Apply filtering
    mask = pd.Series(True, index=full_df.index)
    if sel_year != "All Years":
        mask = mask & (full_df["Date"].dt.year == int(sel_year))
    if sel_month != "All Months":
        m_idx = int(sel_month.split()[0])
        mask = mask & (full_df["Date"].dt.month == m_idx)

    view_df = full_df[mask].reset_index(drop=True)
    st.caption(f"Showing **{len(view_df)}** of **{len(full_df)}** fuel price entries")

    edited_view = st.data_editor(
        view_df,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", required=True),
            "Price (THB/L)": st.column_config.NumberColumn("Price (THB/L)", min_value=0.0, max_value=99.99, format="%.2f", required=True),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key="fp_data_editor"
    )

    if edited_view is not None:
        other_rows = full_df[~mask]
        merged_df = pd.concat([other_rows, edited_view], ignore_index=True)
        merged_df = merged_df.drop_duplicates(subset=["Date"], keep="last").sort_values("Date").reset_index(drop=True)
        st.session_state[fp_key] = merged_df

    fc1, fc2, fc3 = st.columns([1, 1, 3])
    with fc1:
        if st.button("💾 Save", type="primary", use_container_width=True):
            df = st.session_state[fp_key]
            records = df.to_dict("records") if isinstance(df, pd.DataFrame) else list(df)
            new_prices = {}
            for r in records:
                dt = r.get("Date")
                pr = r.get("Price (THB/L)")
                if dt is not None and pd.notna(dt) and pr is not None and pd.notna(pr):
                    key = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                    new_prices[key] = float(pr)
            fp["prices"] = new_prices
            save_json(DATA_DIR / "ptt_fuel_prices.json", fp)
            st.success(f"✅ Saved {len(new_prices)} price entries")
            st.rerun()
    with fc2:
        if st.button("📡 Fetch", use_container_width=True):
            st.session_state._md_show_fetch = not st.session_state.get("_md_show_fetch", False)

if st.session_state.get("_md_show_fetch", False):
    with st.container(border=True):
        months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                     "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
        from datetime import date as dt_date
        mf1, mf2, mf3 = st.columns([1, 1, 1])
        with mf1:
            f_year = st.number_input("Year (พ.ศ.)", value=dt_date.today().year + 543,
                                     min_value=2560, max_value=2600, step=1)
        with mf2:
            f_month = st.selectbox("Month", list(range(1, 13)),
                                   format_func=lambda m: f"{m:02d} ({months_th[m-1]})")
        with mf3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("📡 Fetch from PTT", type="primary", use_container_width=True):
                with st.spinner("Fetching..."):
                    fp_result, added = fetch_month_from_ptt(int(f_year), int(f_month))
                    if fp_result is None:
                        st.error("PTT API returned no data for this month")
                    else:
                        st.success(f"✅ Fetched — {added} new entries added")
                        st.session_state.pop(fp_key, None)
                        st.rerun()

# ── Audit Log ──
with st.expander("📋 Activity Log", expanded=False):
    log_entries = get_activity_log(100)
    if not log_entries:
        st.caption("No activity recorded yet.")
    else:
        for entry in reversed(log_entries):
            ts = entry["timestamp"][:19].replace("T", " ")
            st.markdown(
                f'<div style="font-size:0.75rem;padding:0.25rem 0;border-bottom:1px solid #f1f5f9">'
                f'<span style="color:#64748b">{ts}</span> '
                f'<span style="font-weight:600">{entry["user"]}</span> '
                f'<span style="color:#1a73e8">{entry["action"]}</span>'
                f'<span style="color:#64748b"> — {entry["details"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
