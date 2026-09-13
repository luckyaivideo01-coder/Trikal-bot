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
    digits = re.sub(r'\D', '', str(text))
    if len(digits) == 12 and digits.startswith('91'):
        return digits[2:]
    if len(digits) == 11 and digits.startswith('0'):
        return digits[1:]
    if len(digits) == 10:
        return digits
    if len(digits) > 10:
        return digits[-10:]
    return None

def format_address(address):
    """Format address by removing duplicates and extra spaces."""
    if not address or address == 'N/A':
        return 'N/A'
    # नए API में '!' का इस्तेमाल सेपरेटर के तौर पर हुआ है, उसे स्पेस से बदल दें
    address = str(address).replace('!', ' ')
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

# ---------- fetch_phone_info: AUTO-DETECT ALL API FORMATS ----------
def fetch_phone_info(phone_number):
    """
    Fetch phone details from API. 
    Auto-detects multiple API formats (New & Old) so code doesn't need changing in future.
    Timeout set to 10 seconds.
    """
    url = PHONE_API_NEW.format(num=phone_number)
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"API returned {resp.status_code} for {phone_number}")
            return []

        data = resp.json()

        # =================================================================
        # ========== FORMAT 1: NEW API FORMAT (success, results) ==========
        # =================================================================
        if data.get('success') is True and 'results' in data:
            results = data['results']
            all_records = []
            
            for rec in results:
                normalized = {}
                
                if rec.get('name'): normalized['name'] = str(rec['name'])
                if rec.get('fathersName'): normalized['father_name'] = str(rec['fathersName'])
                if rec.get('address'): normalized['address'] = str(rec['address'])
                if rec.get('phoneNumber'): normalized['mobile'] = normalize_phone_number(rec['phoneNumber'])
                
                if rec.get('otherNumber'):
                    alt = normalize_phone_number(rec['otherNumber'])
                    if alt and alt != normalized.get('mobile'):
                        normalized['alternate_number'] = alt
                
                if rec.get('aadharNumber'): normalized['id'] = str(rec['aadharNumber'])
                
                if rec.get('district'): normalized['circle'] = str(rec['district'])
                elif rec.get('state'): normalized['circle'] = str(rec['state'])
                
                if normalized: all_records.append(normalized)

            # Deduplication for new API format
            seen = set()
            unique_records = []
            for rec in all_records:
                key = (rec.get('mobile', ''), rec.get('name', ''), rec.get('address', '')[:50])
                if key not in seen:
                    seen.add(key)
                    unique_records.append(rec)
            
            if unique_records:
                logger.info(f"✅ Detected New API Format for {phone_number}")
                return unique_records

        # =================================================================
        # ========== FORMAT 2: OLD "NEW" API FORMAT (status, result) ==========
        # =================================================================
        if data.get('status') is True and 'result' in data:
            result_data = data['result']
            all_records = []
            if 'data' in result_data and isinstance(result_data['data'], dict):
                sources = result_data['data']
                for source_key, source_value in sources.items():
                    if isinstance(source_value, dict) and 'records' in source_value:
                        records = source_value['records']
                        if isinstance(records, list):
                            for rec in records:
                                normalized = {}
                                if rec.get('FullName'): normalized['name'] = str(rec['FullName'])
                                if rec.get('FatherName'): normalized['father_name'] = str(rec['FatherName'])
                                if rec.get('Adres'): normalized['address'] = str(rec['Adres'])
                                elif rec.get('Adres2'): normalized['address'] = str(rec['Adres2'])
                                if rec.get('Phone'): normalized['mobile'] = normalize_phone_number(rec['Phone'])
                                if rec.get('Phone2'): 
                                    alt = normalize_phone_number(rec['Phone2'])
                                    if alt and alt != normalized.get('mobile'): normalized['alternate_number'] = alt
                                if rec.get('Region'): normalized['circle'] = str(rec['Region'])
                                if rec.get('DocumentNumber'): normalized['id'] = str(rec['DocumentNumber'])
                                if normalized: all_records.append(normalized)
            
            if all_records:
                logger.info(f"✅ Detected Old 'New' API Format for {phone_number}")
                return all_records

        # =================================================================
        # ========== FORMAT 3: OLD API FORMAT (status: success, data: subscriber) ==========
        # =================================================================
        if data.get('status') == 'success' and 'data' in data:
            subscriber = data['data'].get('subscriber')
            if subscriber and isinstance(subscriber, dict):
                if 'mobile' in subscriber:
                    subscriber['mobile'] = normalize_phone_number(subscriber['mobile']) or subscriber['mobile']
                if 'alternate_number' in subscriber:
                    subscriber['alternate_number'] = normalize_phone_number(subscriber['alternate_number']) or subscriber['alternate_number']
                logger.info(f"✅ Detected Old API Format 1 for {phone_number}")
                return [subscriber]

        # =================================================================
        # ========== FORMAT 4: OLD API FORMAT (Direct List) ==========
        # =================================================================
        if isinstance(data, list):
            for rec in data:
                if isinstance(rec, dict):
                    if 'mobile' in rec:
                        rec['mobile'] = normalize_phone_number(rec['mobile']) or rec['mobile']
                    if 'alternate_number' in rec:
                        rec['alternate_number'] = normalize_phone_number(rec['alternate_number']) or rec['alternate_number']
            logger.info(f"✅ Detected Old API Format 2 (List) for {phone_number}")
            return data

        # =================================================================
        # ========== FORMAT 5: OLD API FORMAT (records key) ==========
        # =================================================================
        if isinstance(data, dict) and 'records' in data:
            records = data['records']
            for rec in records:
                if isinstance(rec, dict):
                    if 'mobile' in rec:
                        rec['mobile'] = normalize_phone_number(rec['mobile']) or rec['mobile']
                    if 'alternate_number' in rec:
                        rec['alternate_number'] = normalize_phone_number(rec['alternate_number']) or rec['alternate_number']
            logger.info(f"✅ Detected Old API Format 3 (Records Key) for {phone_number}")
            return records

        # अगर कोई भी फॉर्मेट मैच नहीं हुआ
        logger.warning(f"⚠️ No matching API format or data found for {phone_number}")
        return []

    except requests.exceptions.Timeout:
        logger.warning(f"⏱️ API timeout for {phone_number} (10s)")
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
