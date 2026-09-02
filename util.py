import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PTT_AJAX_URL = "https://www.pttor.com/wp-admin/admin-ajax.php"
PTT_OIL_TYPE = "ดีเซล"
BACKUP_DIR = DATA_DIR / "backups"
AUDIT_LOG = DATA_DIR / "audit_log.jsonl"
USERS_FILE = DATA_DIR / "users.json"
VERSION_FILE = DATA_DIR / ".version"


# ── Helpers ──

def _fetch_ptt_month(year_be, month):
    import requests as req
    import calendar
    from datetime import date
    try:
        resp = req.post(PTT_AJAX_URL, data={
            "action": "fetch_oil_prices",
            "province": "กรุงเทพมหานคร",
            "month": str(month),
            "year": str(year_be),
        }, headers={
            "X-Requested-With": "XMLHttpRequest",
        }, timeout=10)
        result = resp.json()
    except Exception:
        return None, None

    if not result.get("success"):
        return None, None

    year_ce = year_be - 543
    raw_events = {}
    for day_data in result.get("data", []):
        day_num = day_data.get("day")
        if day_num is None:
            continue
        diesel_price = None
        for oil in day_data.get("priceData", []):
            if oil.get("OilTypeId") in (PTT_OIL_TYPE, "ดีเซล", "Standard Diesel", "Diesel"):
                diesel_price = oil.get("Price")
                break
        if diesel_price is not None:
            try:
                d = date(year_ce, month, int(day_num))
                raw_events[d.isoformat()] = float(diesel_price)
            except (ValueError, TypeError):
                continue

    if not raw_events:
        return None, None

    num_days = calendar.monthrange(year_ce, month)[1]
    filled_prices = {}
    last_price = None
    for day_idx in range(1, num_days + 1):
        iso_str = f"{year_ce:04d}-{month:02d}-{day_idx:02d}"
        if iso_str in raw_events:
            last_price = raw_events[iso_str]
            filled_prices[iso_str] = last_price
        elif last_price is not None:
            filled_prices[iso_str] = last_price

    filled_prices.update(raw_events)
    return filled_prices, raw_events


def fetch_month_from_ptt(year_be, month):
    prices_tuple = _fetch_ptt_month(year_be, month)
    if not prices_tuple or not prices_tuple[0]:
        return None, 0
    prices, raw_events = prices_tuple
    fp = load_json(DATA_DIR / "ptt_fuel_prices.json")
    before = len(fp.get("prices", {}))
    if "prices" not in fp:
        fp["prices"] = {}
    fp["prices"].update(prices)

    actual_dates = set(fp.get("actual_dates", []))
    if raw_events:
        actual_dates.update(raw_events.keys())
    fp["actual_dates"] = sorted(list(actual_dates))

    save_json(DATA_DIR / "ptt_fuel_prices.json", fp)
    added = len(fp["prices"]) - before
    return fp, added


def ensure_fuel_price_auto(d):
    """
    Checks if date d has an actual recorded fuel price in ptt_fuel_prices.json.
    If missing or forward-filled from an older date (and d <= date.today()),
    auto-fetches from PTT API to overwrite/update with the actual official price.
    """
    from datetime import date as dt_date
    iso_str = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
    fp = load_json(DATA_DIR / "ptt_fuel_prices.json")
    prices = fp.get("prices", {})
    actual_dates = set(fp.get("actual_dates", []))

    today = dt_date.today()
    needs_fetch = (iso_str not in prices) or (iso_str not in actual_dates and d <= today)

    if needs_fetch:
        year_be = d.year + 543
        updated_fp, added = fetch_month_from_ptt(year_be, d.month)
        if updated_fp:
            fp = updated_fp
            prices = fp.get("prices", {})
            actual_dates = set(fp.get("actual_dates", []))

    return prices.get(iso_str), iso_str in actual_dates


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def find_tier(tiers, diesel_price):
    for t in tiers:
        if t["min"] <= diesel_price <= t["max"]:
            return t
    return None


def find_band(bands, diesel_price):
    for b in bands:
        if b["min"] <= diesel_price <= b["max"]:
            return b
    return None


def format_thb(v):
    return f"{v:,.2f}"


def match_kiswire_customer(route_display, vendor_name, et_route_id, customer_list):
    if not route_display:
        return None

    r_orig = route_display.lower()
    r_norm = r_orig.replace(" ", "").replace("-", "").replace("→", "").replace("↔", "")
    v_norm = (vendor_name or "").lower()


    # 1. Location-Specific Michelin Matching
    if "michelin" in r_orig or "มิชลิน" in r_orig or "sfc" in r_orig or "phrasamutchedi" in r_norm:
        if "nongkhae" in r_norm or "saraburi" in r_norm or "หนองแค" in r_orig:
            for i, c in enumerate(customer_list):
                if c["customer"] == "MICHELIN SIAM CO.,LTD." and "sara" in c["location"].lower():
                    return i
        if "phrapradaeng" in r_norm or "ppd" in r_norm or "samutprakan" in r_norm or "พระประแดง" in r_orig or "sfc" in r_norm or "phrasamutchedi" in r_norm:
            for i, c in enumerate(customer_list):
                if c["customer"] == "MICHELIN SIAM CO.,LTD." and "phrapradeang" in c["location"].lower().replace(" ", ""):
                    return i
        if "laemchabang" in r_norm or "lcb" in r_norm or "lch" in r_norm or "chonburi" in r_norm or "แหลมฉบัง" in r_orig:
            for i, c in enumerate(customer_list):
                if c["customer"] == "MICHELIN SIAM CO.,LTD." and ("chon" in c["location"].lower() or "lamung" in c["location"].lower()):
                    return i

    # 2. Specific Bridgestone Matching
    if "bridgestone" in r_orig:
        if "ncr" in r_orig or "industrial" in r_orig:
            for i, c in enumerate(customer_list):
                if "INDUSTRIAL" in c["customer"] or "NCR" in c["customer"]:
                    return i
        if "tire" in r_orig or "amata" in r_orig or "chonburi" in r_norm:
            for i, c in enumerate(customer_list):
                if "TIRE MANUFACTURING" in c["customer"] and "BRIDGESTONE" in c["customer"]:
                    return i
        if "nongkhae" in r_norm or "saraburi" in r_norm or "thai" in r_norm:
            for i, c in enumerate(customer_list):
                if c["customer"] == "THAI BRIDGESTONE":
                    return i
        for i, c in enumerate(customer_list):
            if c["customer"] == "THAI BRIDGESTONE":
                return i

    # 3. Direct Customer Keyword Aliases
    aliases = [
        (["otaniradial", "otanitire", "otani"], "OTANI RADIAL CO.,LTD."),
        (["svizzone", "svizz"], "SVIZZ ONE CO.,LTD."),
        (["veerubber", "thasai"], "VEE RUBBER CO.,LTD."),
        (["victoriatyres", "liontyre", "bangpu"], "LION TYRE CO.,LTD."),
        (["sumitomorubber", "sumitomo"], "SUMITOMO CO.,LTD."),
        (["srtyres", "srtyre", "lenzing"], "SR TYRE CO.,LTD."),
        (["continentaltyres", "continental"], "CONTINENTAL TYRES (THAILAND) CO., LTD."),
        (["goodyear"], "GOOD YEAR"),
        (["inouerubber", "inoue"], "INOUE RUBBER"),
        (["maxxis"], "MAXXIS  CO.,LTD."),
        (["semperflex"], "SEMPERFLEX"),
        (["siamtruck"], "SIAMTRUCK RADIAL"),
        (["yokohama"], "YOKOHAMA TIRE MANUFACTURING (THAILAND) CO.,LTD."),
    ]

    for keywords, cname in aliases:
        for kw in keywords:
            if kw in r_norm:
                for i, c in enumerate(customer_list):
                    if c["customer"] == cname:
                        return i

    # 4. Assawa specific fallback
    if "assawa" in v_norm:
        if "bridgestone" in r_norm:
            for i, c in enumerate(customer_list):
                if c["customer"] == "THAI BRIDGESTONE":
                    return i
        if "thasai" in r_norm or "samutsakhon" in r_norm:
            for i, c in enumerate(customer_list):
                if c["customer"] == "VEE RUBBER CO.,LTD.":
                    return i
        if "sfc" in r_norm or "phrasamutchedi" in r_norm:
            for i, c in enumerate(customer_list):
                if c["customer"] == "MICHELIN SIAM CO.,LTD." and "phrapradeang" in c["location"].lower().replace(" ", ""):
                    return i

    if et_route_id:
        return None

    # Fallback to customer name substring
    for i, c in enumerate(customer_list):
        nc = c["customer"].lower().replace(" ", "").replace("-", "").replace("co.,ltd.", "").replace("co.,ltd", "").replace("ltd.", "").replace("ltd", "")
        if len(nc) >= 4 and nc in r_norm:
            return i

    return None


# ── Enterprise: Authentication ──

def _ensure_users_file():
    if not USERS_FILE.exists():
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_users = {
            "users": [
                {"username": "admin", "password_hash": hashlib.sha256("admin".encode()).hexdigest(), "role": "admin", "display": "Administrator"},
                {"username": "user", "password_hash": hashlib.sha256("user".encode()).hexdigest(), "role": "viewer", "display": "User"},
            ]
        }
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_users, f, indent=2)
        return default_users
    with open(USERS_FILE, encoding="utf-8-sig") as f:
        return json.load(f)


def authenticate(username, password):
    data = _ensure_users_file()
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    for u in data["users"]:
        stored = u["password_hash"]
        if u["username"] == username and (stored == pw_hash or stored == password):
            return u
    return None


def get_users():
    data = _ensure_users_file()
    return data["users"]


def save_user(username, password=None, role="admin", display=None, author="system"):
    data = _ensure_users_file()
    users = data.get("users", [])
    display = display or username
    found = False
    for u in users:
        if u["username"] == username:
            found = True
            u["role"] = role
            u["display"] = display
            if password:
                u["password_hash"] = hashlib.sha256(password.encode()).hexdigest()
            break
    if not found:
        pw = password if password else username
        users.append({
            "username": username,
            "password_hash": hashlib.sha256(pw.encode()).hexdigest(),
            "role": role,
            "display": display
        })
        log_activity(author, "user_created", f"Created user '{username}' ({role})")
    else:
        log_activity(author, "user_updated", f"Updated user '{username}' ({role})")
    data["users"] = users
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True


def delete_user(username, author="system"):
    data = _ensure_users_file()
    users = data.get("users", [])
    new_users = [u for u in users if u["username"] != username]
    if len(new_users) == len(users):
        return False, "User not found"
    if len(new_users) == 0:
        return False, "Cannot delete the last remaining user"
    data["users"] = new_users
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log_activity(author, "user_deleted", f"Deleted user '{username}'")
    return True, "User deleted successfully"



# ── Enterprise: Audit Log ──

def log_activity(username, action, details=""):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": username,
        "action": action,
        "details": details,
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_activity_log(limit=50):
    if not AUDIT_LOG.exists():
        return []
    entries = []
    with open(AUDIT_LOG, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-limit:]


# ── Enterprise: Version tracking (cache busting) ──

def _bump_version():
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(str(datetime.now().timestamp()), encoding="utf-8")


def _read_version():
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0"


# ── Enterprise: Auto-backup ──

def _backup_master():
    src = DATA_DIR / "quotation_master.json"
    if not src.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"quotation_master_{ts}.json"
    shutil.copy2(src, dst)
    # Keep only last 50 backups
    backups = sorted(BACKUP_DIR.glob("quotation_master_*.json"), reverse=True)
    for b in backups[50:]:
        b.unlink()


# ── Master file helpers ──

def _load_master():
    with open(DATA_DIR / "quotation_master.json", encoding="utf-8-sig") as f:
        return json.load(f)


def _save_master(master):
    _backup_master()
    with open(DATA_DIR / "quotation_master.json", "w", encoding="utf-8") as f:
        json.dump(master, f, indent=2, ensure_ascii=False)
    _bump_version()


def _save_vendor_to_master(name, data, username="system"):
    master = _load_master()
    master["vendors"][name] = data
    _save_master(master)
    log_activity(username, "vendor_saved", f"Vendor '{name}'")


def _delete_vendor_from_master(name, username="system"):
    master = _load_master()
    master["vendors"].pop(name, None)
    _save_master(master)
    log_activity(username, "vendor_deleted", f"Vendor '{name}'")


def _save_route_to_master(vendor_name, route, append=False, old_display=None, username="system"):
    master = _load_master()
    routes = master["vendors"][vendor_name]["routes"]
    if append:
        routes.append(route)
        log_activity(username, "route_added", f"Route '{route['display']}' → {vendor_name}")
    else:
        for i, r in enumerate(routes):
            if r["display"] == (old_display or route["display"]):
                routes[i] = route
                break
        log_activity(username, "route_saved", f"Route '{route['display']}' → {vendor_name}")
    _save_master(master)


def _delete_route_from_master(vendor_name, display_name, username="system"):
    master = _load_master()
    routes = master["vendors"][vendor_name]["routes"]
    master["vendors"][vendor_name]["routes"] = [r for r in routes if r["display"] != display_name]
    _save_master(master)
    log_activity(username, "route_deleted", f"Route '{display_name}' from {vendor_name}")


def _save_bands_to_master(vendor_name, route_display, bands, username="system"):
    master = _load_master()
    for r in master["vendors"][vendor_name]["routes"]:
        if r["display"] == route_display:
            r["bands"] = bands
            break
    _save_master(master)
    log_activity(username, "bands_saved", f"Price tiers for {vendor_name} → {route_display}")


def export_master_to_excel(master):
    import io
    import pandas as pd
    rows = []
    vendors = master.get("vendors", {})
    for vname, vdata in vendors.items():
        company = vdata.get("company", vname)
        routes = vdata.get("routes", [])
        if not routes:
            rows.append({
                "Vendor": vname,
                "Company": company,
                "Route ID": "",
                "Route": "",
                "Min Diesel (THB/L)": 0.0,
                "Max Diesel (THB/L)": 99.99,
                "Rate (THB)": 0.0,
                "Is ET Route": False,
                "ET Route ID": ""
            })
        else:
            for r in routes:
                rid = r.get("id", "")
                rdisplay = r.get("display", "")
                is_et = r.get("is_et_route", False)
                et_id = r.get("et_route_id", "")
                bands = r.get("bands", [])
                if not bands:
                    rows.append({
                        "Vendor": vname,
                        "Company": company,
                        "Route ID": rid,
                        "Route": rdisplay,
                        "Min Diesel (THB/L)": 0.0,
                        "Max Diesel (THB/L)": 99.99,
                        "Rate (THB)": 0.0,
                        "Is ET Route": is_et,
                        "ET Route ID": et_id
                    })
                else:
                    for b in bands:
                        rows.append({
                            "Vendor": vname,
                            "Company": company,
                            "Route ID": rid,
                            "Route": rdisplay,
                            "Min Diesel (THB/L)": float(b.get("min", 0)),
                            "Max Diesel (THB/L)": float(b.get("max", 99.99)),
                            "Rate (THB)": float(b.get("rate", 0)),
                            "Is ET Route": is_et,
                            "ET Route ID": et_id
                        })

    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Master Data")
    return buf.getvalue()


def import_master_from_excel(file_obj, username="system"):
    import pandas as pd
    if hasattr(file_obj, "name") and file_obj.name.lower().endswith(".csv"):
        df = pd.read_csv(file_obj)
    else:
        df = pd.read_excel(file_obj)

    if df.empty:
        return False, "File is empty."

    col_map = {}
    for c in df.columns:
        clower = str(c).strip().lower()
        if "vendor" in clower:
            col_map["vendor"] = c
        elif "company" in clower:
            col_map["company"] = c
        elif "route id" in clower or "route_id" in clower or clower == "id":
            col_map["route_id"] = c
        elif "route" in clower and "et" not in clower:
            col_map["route"] = c
        elif "min" in clower:
            col_map["min"] = c
        elif "max" in clower:
            col_map["max"] = c
        elif "rate" in clower or "price" in clower or "cost" in clower:
            col_map["rate"] = c
        elif "is et" in clower or "et route" in clower:
            col_map["is_et"] = c
        elif "et" in clower and "id" in clower:
            col_map["et_id"] = c

    if "vendor" not in col_map or "route" not in col_map or "rate" not in col_map:
        return False, "Missing required columns in Excel. Headers must include 'Vendor', 'Route', and 'Rate (THB)'."

    master = _load_master()
    import re
    existing_vendors = master.get("vendors", {})
    norm_vendor_map = {re.sub(r'\s+', ' ', v).strip().upper(): v for v in existing_vendors.keys()}

    routes_cfg = load_json(DATA_DIR / "canonical_routes.json")
    canon_routes = routes_cfg.get("et_routes", [])
    canon_map = {re.sub(r'\s+', ' ', r["display"]).strip().lower(): r["id"] for r in canon_routes}
    canon_ids = {r["id"] for r in canon_routes}

    new_vendors = {}

    for idx, row in df.iterrows():
        raw_v = str(row[col_map["vendor"]]) if pd.notna(row[col_map["vendor"]]) else ""
        norm_v = re.sub(r'\s+', ' ', raw_v).strip().upper()
        if not norm_v or norm_v.startswith("—") or norm_v == "NAN":
            continue

        vname = norm_vendor_map.get(norm_v, norm_v)

        company = re.sub(r'\s+', ' ', str(row[col_map["company"]])).strip() if "company" in col_map and pd.notna(row[col_map["company"]]) else vname
        raw_r = str(row[col_map["route"]]) if pd.notna(row[col_map["route"]]) else ""
        clean_r = re.sub(r'\s+', ' ', raw_r).strip()
        route_id = str(row[col_map["route_id"]]).strip() if "route_id" in col_map and pd.notna(row[col_map["route_id"]]) else ""

        try:
            rmin = float(row[col_map["min"]]) if "min" in col_map and pd.notna(row[col_map["min"]]) else 0.0
        except (ValueError, TypeError):
            rmin = 0.0

        try:
            rmax = float(row[col_map["max"]]) if "max" in col_map and pd.notna(row[col_map["max"]]) else 99.99
        except (ValueError, TypeError):
            rmax = 99.99

        try:
            rrate = float(row[col_map["rate"]]) if pd.notna(row[col_map["rate"]]) else 0.0
        except (ValueError, TypeError):
            rrate = 0.0

        is_et_given = "is_et" in col_map and pd.notna(row[col_map["is_et"]])
        is_et = False
        if is_et_given:
            val_et = str(row[col_map["is_et"]]).strip().upper()
            is_et = val_et in ["TRUE", "1", "YES"]

        et_id = ""
        if "et_id" in col_map and pd.notna(row[col_map["et_id"]]):
            et_id = str(row[col_map["et_id"]]).strip()

        if vname not in new_vendors:
            old_routes = existing_vendors.get(vname, {}).get("routes", [])
            id_route_map = {r.get("id"): r["display"] for r in old_routes if r.get("id")}
            old_route_objs = {r.get("id"): r for r in old_routes if r.get("id")}
            norm_route_map = {re.sub(r'\s+', ' ', r["display"]).strip().lower(): r["display"] for r in old_routes}
            norm_route_objs = {re.sub(r'\s+', ' ', r["display"]).strip().lower(): r for r in old_routes}
            new_vendors[vname] = {
                "company": company,
                "notes": existing_vendors.get(vname, {}).get("notes", ""),
                "id_route_map": id_route_map,
                "old_route_objs": old_route_objs,
                "norm_route_map": norm_route_map,
                "norm_route_objs": norm_route_objs,
                "routes": {}
            }

        if clean_r or route_id:
            id_map = new_vendors[vname]["id_route_map"]
            norm_map = new_vendors[vname]["norm_route_map"]
            old_objs_id = new_vendors[vname]["old_route_objs"]
            old_objs_norm = new_vendors[vname]["norm_route_objs"]

            old_r_obj = None
            if route_id and route_id in id_map:
                rdisplay = clean_r or id_map[route_id]
                rid = route_id
                old_r_obj = old_objs_id.get(route_id)
            elif clean_r.lower() in norm_map:
                rdisplay = norm_map[clean_r.lower()]
                rid = route_id or rdisplay.lower().replace(" ", "_").replace("→", "to")
                rid = "".join(c if c.isalnum() or c == "_" else "_" for c in rid)
                old_r_obj = old_objs_norm.get(clean_r.lower())
            else:
                rdisplay = clean_r
                rid = route_id or rdisplay.lower().replace(" ", "_").replace("→", "to")
                rid = "".join(c if c.isalnum() or c == "_" else "_" for c in rid)

            # Preserve or auto-detect ET route ID for HQ pricing
            if not et_id and old_r_obj:
                et_id = old_r_obj.get("et_route_id", "")
            if not et_id:
                et_id = canon_map.get(rdisplay.lower(), canon_map.get(clean_r.lower(), ""))

            if not is_et_given:
                if old_r_obj and "is_et_route" in old_r_obj:
                    is_et = old_r_obj["is_et_route"]
                else:
                    is_et = bool(et_id)
            elif et_id and not is_et:
                is_et = True

            v_routes = new_vendors[vname]["routes"]
            if rdisplay not in v_routes:
                v_routes[rdisplay] = {
                    "id": rid,
                    "display": rdisplay,
                    "is_et_route": is_et,
                    "bands": {}
                }
                if et_id:
                    v_routes[rdisplay]["et_route_id"] = et_id

            v_routes[rdisplay]["bands"][(rmin, rmax)] = rrate

    final_vendors = {}
    total_routes = 0
    total_bands = 0
    for vname, vdict in new_vendors.items():
        route_list = []
        for rdisp, rdata in vdict["routes"].items():
            bands_dict = rdata["bands"]
            sorted_bands = [{"min": p[0], "max": p[1], "rate": r} for p, r in sorted(bands_dict.items(), key=lambda x: x[0][0])]
            rdata["bands"] = sorted_bands
            route_list.append(rdata)
            total_routes += 1
            total_bands += len(sorted_bands)
        final_vendors[vname] = {
            "company": vdict["company"],
            "notes": vdict["notes"],
            "routes": route_list
        }

    master["vendors"] = final_vendors
    _save_master(master)
    log_activity(username, "excel_imported", f"Imported {len(final_vendors)} vendors, {total_routes} routes, {total_bands} bands")
    return True, f"✅ Master Data updated! Imported {len(final_vendors)} vendors, {total_routes} routes, and {total_bands} price tiers."


def check_duplicate_rates(master):
    """
    Scans quotation_master.json for duplicate or overlapping price tiers within each route.
    Returns a list of issue dictionaries.
    """
    issues = []
    vendors = master.get("vendors", {})
    for vname, vdata in vendors.items():
        for r in vdata.get("routes", []):
            rdisp = r.get("display", "")
            bands = r.get("bands", [])
            seen_ranges = {}
            for i, b in enumerate(bands):
                rmin, rmax, rrate = b.get("min"), b.get("max"), b.get("rate")
                pair = (rmin, rmax)
                if pair in seen_ranges:
                    prev_rate = seen_ranges[pair]["rate"]
                    issues.append({
                        "vendor": vname,
                        "route": rdisp,
                        "type": "exact_duplicate",
                        "detail": f"Duplicate range [{rmin:.2f} - {rmax:.2f}] THB/L with rates {prev_rate:,.2f} and {rrate:,.2f} THB"
                    })
                else:
                    seen_ranges[pair] = {"rate": rrate, "index": i}

            sorted_bands = sorted(bands, key=lambda x: (x.get("min", 0), x.get("max", 0)))
            for j in range(len(sorted_bands) - 1):
                b1 = sorted_bands[j]
                b2 = sorted_bands[j + 1]
                if b1.get("max", 0) > b2.get("min", 0) and (b1.get("min"), b1.get("max")) != (b2.get("min"), b2.get("max")):
                    issues.append({
                        "vendor": vname,
                        "route": rdisp,
                        "type": "overlapping_range",
                        "detail": f"Overlapping ranges [{b1.get('min'):.2f} - {b1.get('max'):.2f}] and [{b2.get('min'):.2f} - {b2.get('max'):.2f}] THB/L"
                    })
    return issues


def deduplicate_master_rates(master, username="system"):
    """
    Removes exact duplicate ranges within each route, keeping the last recorded rate.
    """
    vendors = master.get("vendors", {})
    cleaned_count = 0
    for vname, vdata in vendors.items():
        for r in vdata.get("routes", []):
            bands = r.get("bands", [])
            unique_bands = {}
            for b in bands:
                pair = (float(b.get("min", 0)), float(b.get("max", 0)))
                unique_bands[pair] = float(b.get("rate", 0))

            if len(unique_bands) < len(bands):
                cleaned_count += (len(bands) - len(unique_bands))
                new_bands = [{"min": p[0], "max": p[1], "rate": r} for p, r in sorted(unique_bands.items(), key=lambda x: x[0][0])]
                r["bands"] = new_bands

    if cleaned_count > 0:
        _save_master(master)
        log_activity(username, "rates_deduplicated", f"Removed {cleaned_count} duplicate price tiers")

    return cleaned_count
