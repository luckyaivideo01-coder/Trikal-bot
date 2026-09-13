import re
import html
import json
import requests
import logging
from io import BytesIO
from datetime import datetime
from config import PHONE_API_NEW

logger = logging.getLogger(__name__)

def normalize_phone_number(text):
    """Convert any phone number to 10-digit Indian format."""
    if not text:
        return None
    # Remove non-digit characters
    digits = re.sub(r'\D', '', str(text))
    # If it starts with 91, remove it
    if len(digits) == 12 and digits.startswith('91'):
        return digits[2:]
    # If it starts with 0, remove it
    if len(digits) == 11 and digits.startswith('0'):
        return digits[1:]
    # If it's 10 digits, return as is
    if len(digits) == 10:
        return digits
    # If longer, take last 10
    if len(digits) > 10:
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

# ---------- fetch_phone_info with deduplication & normalization ----------
def fetch_phone_info(phone_number):
    """
    Fetch phone details from new API.
    Returns a list of unique subscriber dicts with normalized numbers.
    Timeout set to 5 seconds.
    """
    url = PHONE_API_NEW.format(num=phone_number)
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            logger.warning(f"API returned {resp.status_code} for {phone_number}")
            return []

        data = resp.json()

        # ========== NEW API FORMAT (multiple sources) ==========
        if data.get('status') is True and 'result' in data:
            result_data = data['result']
            all_records = []
            if 'data' in result_data and isinstance(result_data['data'], dict):
                sources = result_data['data']
                for source_key, source_value in sources.items():
                    if isinstance(source_value, dict) and 'records' in source_value:
                        records = source_value['records']
                        if not isinstance(records, list):
                            continue
                        for rec in records:
                            normalized = {}
                            # Map fields
                            if 'FullName' in rec and rec['FullName']:
                                normalized['name'] = str(rec['FullName'])
                            if 'FatherName' in rec and rec['FatherName']:
                                normalized['father_name'] = str(rec['FatherName'])
                            if 'Adres' in rec and rec['Adres']:
                                normalized['address'] = str(rec['Adres'])
                            elif 'Adres2' in rec and rec['Adres2']:
                                normalized['address'] = str(rec['Adres2'])
                            # Phone numbers: normalize to 10 digits
                            phone = None
                            if 'Phone' in rec and rec['Phone']:
                                phone = normalize_phone_number(rec['Phone'])
                            elif 'Phone2' in rec and rec['Phone2']:
                                phone = normalize_phone_number(rec['Phone2'])
                            elif 'Phone3' in rec and rec['Phone3']:
                                phone = normalize_phone_number(rec['Phone3'])
                            if phone:
                                normalized['mobile'] = phone
                            # Alternate number
                            alt = None
                            if 'Phone2' in rec and rec['Phone2']:
                                alt = normalize_phone_number(rec['Phone2'])
                            elif 'Phone3' in rec and rec['Phone3']:
                                alt = normalize_phone_number(rec['Phone3'])
                            # Avoid same as mobile
                            if alt and alt == normalized.get('mobile'):
                                alt = None
                            if alt:
                                normalized['alternate_number'] = alt
                            # Circle/Region
                            if 'Region' in rec and rec['Region']:
                                normalized['circle'] = str(rec['Region'])
                            elif 'Stat' in rec and rec['Stat']:
                                normalized['circle'] = str(rec['Stat'])
                            # ID
                            if 'DocumentNumber' in rec and rec['DocumentNumber']:
                                normalized['id'] = str(rec['DocumentNumber'])
                            # Age or other fields could be added
                            if normalized:
                                all_records.append(normalized)

            # ----- DEDUPLICATION -----
            seen = set()
            unique_records = []
            for rec in all_records:
                # Create a unique key based on mobile and name (and address if available)
                mobile = rec.get('mobile', '')
                name = rec.get('name', '')
                address = rec.get('address', '')
                key = (mobile, name, address[:50])  # limit address length
                if key not in seen:
                    seen.add(key)
                    unique_records.append(rec)
            if unique_records:
                return unique_records

        # ========== OLD API FORMAT 1 ==========
        if data.get('status') == 'success' and 'data' in data:
            subscriber = data['data'].get('subscriber')
            if subscriber and isinstance(subscriber, dict):
                # Normalize mobile if present
                if 'mobile' in subscriber:
                    subscriber['mobile'] = normalize_phone_number(subscriber['mobile']) or subscriber['mobile']
                if 'alternate_number' in subscriber:
                    subscriber['alternate_number'] = normalize_phone_number(subscriber['alternate_number']) or subscriber['alternate_number']
                return [subscriber]

        # ========== OLD FORMAT 2 (direct list) ==========
        if isinstance(data, list):
            # Normalize each entry
            for rec in data:
                if isinstance(rec, dict):
                    if 'mobile' in rec:
                        rec['mobile'] = normalize_phone_number(rec['mobile']) or rec['mobile']
                    if 'alternate_number' in rec:
                        rec['alternate_number'] = normalize_phone_number(rec['alternate_number']) or rec['alternate_number']
            return data

        # ========== OLD FORMAT 3 (records key) ==========
        if isinstance(data, dict) and 'records' in data:
            records = data['records']
            for rec in records:
                if isinstance(rec, dict):
                    if 'mobile' in rec:
                        rec['mobile'] = normalize_phone_number(rec['mobile']) or rec['mobile']
                    if 'alternate_number' in rec:
                        rec['alternate_number'] = normalize_phone_number(rec['alternate_number']) or rec['alternate_number']
            return records

        logger.warning(f"⚠️ No data found for {phone_number}")
        return []

    except requests.exceptions.Timeout:
        logger.warning(f"⏱️ API timeout for {phone_number} (5s)")
        return []
    except requests.exceptions.ConnectionError:
        logger.warning(f"🔌 API connection error for {phone_number}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON decode error: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ API error: {e}")
        return []
