import re
import html
import requests
import logging
from io import BytesIO
from datetime import datetime
from config import PHONE_API_NEW

logger = logging.getLogger(__name__)

def normalize_phone_number(text):
    digits = re.sub(r'\D', '', text)
    if len(digits) == 10:
        return digits
    elif len(digits) == 12 and digits.startswith('91'):
        return digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        return digits[1:] if len(digits[1:]) == 10 else None
    elif len(digits) > 10:
        return digits[-10:]
    return None

def format_address(address):
    if not address or address == 'N/A':
        return 'N/A'
    address = re.sub(r'\s+', ' ', address.strip())
    words = address.split()
    unique = []
    for w in words:
        if w not in unique:
            unique.append(w)
    return ' '.join(unique)

def create_safe_filename(query, search_type, bot_username):
    safe = re.sub(r'[<>:"/\\|?*]', '_', str(query))[:50]
    return f"{search_type}_{safe} @{bot_username}.txt"

def create_search_result_file(result_text, query, search_type, bot_username):
    clean = re.sub(r'<[^>]+>', '', result_text)
    clean = html.unescape(clean)
    content = f"Search Query: {query}\nSearch Type: {search_type}\nGenerated: {datetime.now()}\nBot: @{bot_username}\n{'='*50}\n\n{clean}"
    f = BytesIO(content.encode('utf-8'))
    f.name = create_safe_filename(query, search_type, bot_username)
    return f

def fetch_phone_info(phone_number):   # <-- removed 'async'
    """Universal API parser – works with any response structure."""
    url = PHONE_API_NEW.format(num=phone_number)
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"API returned {resp.status_code}")
            return None
        data = resp.json()
        logger.info(f"Raw API response: {str(data)[:500]}")

        def extract_records(obj, depth=0):
            if depth > 5:
                return None
            if isinstance(obj, dict):
                if any(k in obj for k in ('name', 'mobile', 'address', 'fname', 'phone')):
                    return [obj]
                for v in obj.values():
                    res = extract_records(v, depth+1)
                    if res:
                        return res
            elif isinstance(obj, list):
                if obj and isinstance(obj[0], dict):
                    if any(k in obj[0] for k in ('name', 'mobile', 'address', 'fname')):
                        return obj
                for item in obj:
                    res = extract_records(item, depth+1)
                    if res:
                        return res
            return None

        records = extract_records(data)
        if not records:
            return None

        normalized = []
        field_map = {
            'name': ['name', 'full_name', 'customer_name', 'person_name'],
            'father_name': ['fname', 'father_name', 'father', 'f_name'],
            'address': ['address', 'addr', 'location', 'street'],
            'mobile': ['mobile', 'phone', 'number', 'contact', 'mobileno'],
            'alt_mobile': ['alt', 'alt_mobile', 'alternate', 'phone2'],
            'circle': ['circle', 'operator', 'provider', 'network'],
            'id_number': ['id', 'id_number', 'aadhar', 'uid', 'vid'],
            'email': ['email', 'mail', 'e_mail']
        }
        for rec in records:
            new = {}
            for target, keys in field_map.items():
                for k in keys:
                    if k in rec and rec[k]:
                        new[target] = str(rec[k])
                        break
            for k, v in rec.items():
                if k not in field_map and v:
                    new[k] = v
            if new:
                normalized.append(new)
        return normalized
    except Exception as e:
        logger.error(f"API error: {e}")
        return None
