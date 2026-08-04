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
    with open(path, encoding="utf-8") as f:
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
    rlower = route_display.lower()
    aliases = {
        "otani radial": "OTANI RADIAL CO.,LTD.",
        "otani tire": "OTANI RADIAL CO.,LTD.",
        "svizz": "SVIZZ ONE CO.,LTD.",
        "thai bridgestone": "THAI BRIDGESTONE",
        "bridgestone ncr": "BRIDGESTONE INDUSTRIAL PRODUCTS (THAILAND) CO. LTD. (FORMER: BRIDGESTONE NCR CO.,LTD)",
        "bridgestone industrial": "BRIDGESTONE INDUSTRIAL PRODUCTS (THAILAND) CO. LTD. (FORMER: BRIDGESTONE NCR CO.,LTD)",
        "bridgestone tire": "BRIDGESTONE TIRE MANUFACTURING (THAILAND) CO., LTD.",
        "sumitomo": "SUMITOMO CO.,LTD.",
        "sr tyre": "SR TYRE CO.,LTD.",
        "sr tyres": "SR TYRE CO.,LTD.",
        "continental": "CONTINENTAL TYRES (THAILAND) CO., LTD.",
        "good year": "GOOD YEAR",
        "goodyear": "GOOD YEAR",
        "vee rubber": "VEE RUBBER CO.,LTD.",
        "inoue": "INOUE RUBBER",
    }
    route_patterns = [
        ("michelin siam (ppd)", "MICHELIN SIAM CO.,LTD.", "phrapradeang"),
        ("michelin siam (nong khae", "MICHELIN SIAM CO.,LTD.", "sara buri"),
        ("michelin nongkhae", "MICHELIN SIAM CO.,LTD.", "sara buri"),
        ("michelin lch", "MICHELIN SIAM CO.,LTD.", "chon buri"),
        ("michelin (laem chabang)", "MICHELIN SIAM CO.,LTD.", "chon buri"),
        ("มิชลิน แหลมฉบัง", "MICHELIN SIAM CO.,LTD.", "chon buri"),
        ("มิชลิน หนองแค", "MICHELIN SIAM CO.,LTD.", "sara buri"),
        ("มิชลิน พระประแดง", "MICHELIN SIAM CO.,LTD.", "phrapradeang"),
    ]
    for pattern, cname, loc in route_patterns:
        if pattern in rlower:
            for i, c in enumerate(customer_list):
                if c["customer"] == cname and loc in c["location"].lower():
                    return i
    for kw, cname in aliases.items():
        if kw in rlower:
            for i, c in enumerate(customer_list):
                if c["customer"] == cname:
                    return i
    if et_route_id:
        return None
    sorted_cx = sorted(enumerate(customer_list), key=lambda x: -len(x[1]["customer"]))
    for i, c in sorted_cx:
        nc = c["customer"].lower()
        if len(nc) >= 5 and nc in rlower:
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
    with open(USERS_FILE, encoding="utf-8") as f:
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
    with open(AUDIT_LOG, encoding="utf-8") as f:
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
    with open(DATA_DIR / "quotation_master.json", encoding="utf-8") as f:
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
                "Route": "",
                "Min Diesel (THB/L)": 0.0,
                "Max Diesel (THB/L)": 99.99,
                "Rate (THB)": 0.0,
                "Is ET Route": False,
                "ET Route ID": ""
            })
        else:
            for r in routes:
                rdisplay = r.get("display", "")
                is_et = r.get("is_et_route", False)
                et_id = r.get("et_route_id", "")
                bands = r.get("bands", [])
                if not bands:
                    rows.append({
                        "Vendor": vname,
                        "Company": company,
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
    new_vendors = {}

    for idx, row in df.iterrows():
        vname = str(row[col_map["vendor"]]).strip().upper() if pd.notna(row[col_map["vendor"]]) else ""
        if not vname or vname.startswith("—") or vname == "NAN":
            continue

        company = str(row[col_map["company"]]).strip() if "company" in col_map and pd.notna(row[col_map["company"]]) else vname
        rdisplay = str(row[col_map["route"]]).strip() if pd.notna(row[col_map["route"]]) else ""

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

        is_et = False
        if "is_et" in col_map and pd.notna(row[col_map["is_et"]]):
            val_et = str(row[col_map["is_et"]]).strip().upper()
            is_et = val_et in ["TRUE", "1", "YES"]

        et_id = ""
        if "et_id" in col_map and pd.notna(row[col_map["et_id"]]):
            et_id = str(row[col_map["et_id"]]).strip()

        if vname not in new_vendors:
            new_vendors[vname] = {
                "company": company,
                "notes": master.get("vendors", {}).get(vname, {}).get("notes", ""),
                "routes": {}
            }

        if rdisplay:
            rid = rdisplay.lower().replace(" ", "_").replace("→", "to")
            rid = "".join(c if c.isalnum() or c == "_" else "_" for c in rid)

            v_routes = new_vendors[vname]["routes"]
            if rdisplay not in v_routes:
                v_routes[rdisplay] = {
                    "id": rid,
                    "display": rdisplay,
                    "is_et_route": is_et,
                    "bands": []
                }
                if et_id:
                    v_routes[rdisplay]["et_route_id"] = et_id

            v_routes[rdisplay]["bands"].append({
                "min": rmin,
                "max": rmax,
                "rate": rrate
            })

    final_vendors = {}
    total_routes = 0
    total_bands = 0
    for vname, vdict in new_vendors.items():
        route_list = []
        for rdisp, rdata in vdict["routes"].items():
            route_list.append(rdata)
            total_routes += 1
            total_bands += len(rdata["bands"])
        final_vendors[vname] = {
            "company": vdict["company"],
            "notes": vdict["notes"],
            "routes": route_list
        }

    master["vendors"] = final_vendors
    _save_master(master)
    log_activity(username, "excel_imported", f"Imported {len(final_vendors)} vendors, {total_routes} routes, {total_bands} bands")
    return True, f"✅ Master Data updated! Imported {len(final_vendors)} vendors, {total_routes} routes, and {total_bands} price tiers."


def parse_rate_sheet_file(file_obj, filename):
    import re
    import pandas as pd

    fname = filename.lower()
    records = []

    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(file_obj)
            records = _parse_dataframe_rates(df)
        elif fname.endswith((".xlsx", ".xls")):
            xl = pd.ExcelFile(file_obj)
            for sheet_name in xl.sheet_names:
                df = xl.parse(sheet_name)
                sheet_records = _parse_dataframe_rates(df)
                for r in sheet_records:
                    if not r.get("vendor"):
                        r["vendor"] = sheet_name
                records.extend(sheet_records)
        elif fname.endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(file_obj) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            if not table or len(table) < 2:
                                continue
                            headers = [str(h or f"col_{i}").strip() for i, h in enumerate(table[0])]
                            df = pd.DataFrame(table[1:], columns=headers)
                            records.extend(_parse_dataframe_rates(df))

                        if not records:
                            text = page.extract_text() or ""
                            records.extend(_parse_text_rates(text))
            except Exception:
                pass
    except Exception:
        pass

    return records


def _parse_dataframe_rates(df):
    import re
    import pandas as pd
    records = []
    if df is None or df.empty:
        return records

    cols = [str(c).strip() for c in df.columns]
    df.columns = cols

    col_min, col_max, col_rate, col_route, col_range = None, None, None, None, None
    for c in cols:
        clower = c.lower()
        if any(k in clower for k in ["route", "destination", "เส้นทาง", "ปลายทาง"]):
            col_route = c
        elif any(k in clower for k in ["range", "ช่วงน้ำมัน", "diesel price", "fuel range"]):
            col_range = c
        elif any(k in clower for k in ["min", "ขั้นต่ำ", "จาก"]):
            col_min = c
        elif any(k in clower for k in ["max", "ขั้นสูง", "ถึง"]):
            col_max = c
        elif any(k in clower for k in ["rate", "price", "cost", "charge", "ค่าขนส่ง", "ราคา"]):
            col_rate = c

    for idx, row in df.iterrows():
        r_min, r_max, r_rate = None, None, None
        route_name = str(row[col_route]).strip() if col_route and pd.notna(row[col_route]) else ""

        if col_min and col_max and pd.notna(row[col_min]) and pd.notna(row[col_max]):
            try:
                r_min = float(str(row[col_min]).replace(",", ""))
                r_max = float(str(row[col_max]).replace(",", ""))
            except (ValueError, TypeError):
                pass

        if (r_min is None or r_max is None) and col_range and pd.notna(row[col_range]):
            m = re.search(r'(\d+(?:\.\d+)?)\s*[-~–]\s*(\d+(?:\.\d+)?)', str(row[col_range]))
            if m:
                r_min, r_max = float(m.group(1)), float(m.group(2))

        if col_rate and pd.notna(row[col_rate]):
            clean_str = re.sub(r'[^\d.]', '', str(row[col_rate]).replace(",", ""))
            try:
                if clean_str:
                    r_rate = float(clean_str)
            except (ValueError, TypeError):
                pass

        if (r_min is None or r_rate is None):
            row_str = " ".join([str(val) for val in row.values if pd.notna(val)])
            m_range = re.search(r'(\d+(?:\.\d+)?)\s*[-~–]\s*(\d+(?:\.\d+)?)', row_str)
            m_rate = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b', row_str)
            if m_range and (r_min is None or r_max is None):
                r_min, r_max = float(m_range.group(1)), float(m_range.group(2))
            if m_rate and r_rate is None:
                for num_str in reversed(m_rate):
                    try:
                        v = float(num_str.replace(",", ""))
                        if v > 100 and v != r_min and v != r_max:
                            r_rate = v
                            break
                    except ValueError:
                        pass

        if r_min is not None and r_max is not None and r_rate is not None:
            records.append({
                "route_display": route_name,
                "min": r_min,
                "max": r_max,
                "rate": r_rate
            })

    return records


def _parse_text_rates(text):
    import re
    records = []
    lines = text.splitlines()
    for line in lines:
        m_range = re.search(r'(\d+(?:\.\d+)?)\s*[-~–]\s*(\d+(?:\.\d+)?)', line)
        if not m_range:
            continue
        r_min, r_max = float(m_range.group(1)), float(m_range.group(2))

        nums = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b', line)
        r_rate = None
        for n in reversed(nums):
            try:
                v = float(n.replace(",", ""))
                if v > 100 and v != r_min and v != r_max:
                    r_rate = v
                    break
            except ValueError:
                pass

        if r_min is not None and r_max is not None and r_rate is not None:
            records.append({
                "route_display": "",
                "min": r_min,
                "max": r_max,
                "rate": r_rate
            })
    return records
