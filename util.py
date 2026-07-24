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
    resp = req.post(PTT_AJAX_URL, data={
        "action": "fetch_oil_prices",
        "province": "กรุงเทพมหานคร",
        "month": str(month),
        "year": str(year_be),
    }, headers={
        "X-Requested-With": "XMLHttpRequest",
    }, timeout=10)
    result = resp.json()
    if not result.get("success"):
        return None
    from datetime import date
    prices = {}
    year_ce = year_be - 543
    for day_data in result["data"]:
        day_num = day_data.get("day")
        if day_num is None:
            continue
        diesel_price = None
        for oil in day_data.get("priceData", []):
            if oil.get("OilTypeId") == PTT_OIL_TYPE:
                diesel_price = oil.get("Price")
                break
        if diesel_price is not None:
            try:
                d = date(year_ce, month, int(day_num))
                prices[d.isoformat()] = float(diesel_price)
            except (ValueError, TypeError):
                continue
    return prices


def fetch_month_from_ptt(year_be, month):
    prices = _fetch_ptt_month(year_be, month)
    if not prices:
        return None, 0
    fp = load_json(DATA_DIR / "ptt_fuel_prices.json")
    before = len(fp["prices"])
    fp["prices"].update(prices)
    save_json(DATA_DIR / "ptt_fuel_prices.json", fp)
    added = len(fp["prices"]) - before
    return fp, added


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
