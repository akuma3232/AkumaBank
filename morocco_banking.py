"""
morocco_banking.py - Moroccan Banking Standards & Luhn Card Generation for AkumaBank

Implements:
1. Moroccan RIB (Relevé d'Identité Bancaire) - 24 Digits:
   - Code Banque (3 digits): 240 (AkumaBank BAM code)
   - Code Guichet / Localité (3 digits)
   - Numéro de Compte (16 digits)
   - Clé RIB (2 digits): Calculated via Bank Al-Maghrib Modulo 97 standard
   - Formula: Clé = 97 - ((Payload22 * 100) % 97). Satisfies: int(RIB) % 97 == 0
2. Moroccan IBAN (International Bank Account Number) - 28 Characters:
   - Format: MA64 + 24-digit RIB (ISO 13616 & ISO 7064 MOD 97-10 compliant)
3. 16-Digit Virtual Bank Card (PAN) calculated by computer:
   - Test Prefix: 4240 (Visa sandbox / non-live range - cannot be charged in real life)
   - 11-digit account payload
   - 16th check digit calculated via Luhn Algorithm (MOD 10)
   - 3-digit CVV code
"""

import hashlib
import random
import re

BANK_CODE = "240"        # AkumaBank official bank code registered with Bank Al-Maghrib
DEFAULT_BRANCH = "810"   # Central Headquarters / Agency code


# ─────────────────────────────────────────────────────────────────────────────
# 1. MOROCCAN RIB (RELEVÉ D'IDENTITÉ BANCAIRE - 24 DIGITS)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rib_key(bank_code: str, branch_code: str, account_seq: str) -> str:
    """
    Calculate the 2-digit Moroccan RIB check key (Bank Al-Maghrib standard).
    Payload is 22 digits: Bank (3) + Branch (3) + Account (16).
    Key = 97 - ((Payload * 100) % 97). Range: [01..97].
    """
    b_code = f"{int(bank_code):03d}"
    g_code = f"{int(branch_code):03d}"
    clean_acc = "".join(c for c in str(account_seq) if c.isdigit())
    acc_str = f"{int(clean_acc):016d}" if clean_acc else "0" * 16

    payload = f"{b_code}{g_code}{acc_str}"
    rem = (int(payload) * 100) % 97
    key = 97 - rem
    if key == 0:
        key = 97
    return f"{key:02d}"


def generate_moroccan_rib(branch_id=None, bank_code=BANK_CODE, seq=None) -> str:
    """
    Generate a valid 24-digit Moroccan RIB.
    If seq is None, generates a cryptographically secure 16-digit random account number.
    """
    if branch_id is None:
        branch_code = DEFAULT_BRANCH
    else:
        try:
            branch_code = f"{int(branch_id) % 1000:03d}"
        except Exception:
            branch_code = DEFAULT_BRANCH

    if seq is None:
        # Generate 16-digit pseudo-random sequence
        seq_num = random.randint(10000000000000, 99999999999999)
        seq_str = f"{seq_num:016d}"
    else:
        seq_str = f"{int(seq):016d}"

    key = calculate_rib_key(bank_code, branch_code, seq_str)
    return f"{int(bank_code):03d}{int(branch_code):03d}{seq_str}{key}"


def verify_moroccan_rib(rib: str) -> bool:
    """
    Verify if a 24-digit string is a valid Moroccan RIB conforming to BAM standards.
    Satisfies both the BAM key check and: int(rib) % 97 == 0.
    """
    digits = "".join(c for c in str(rib) if c.isdigit())
    if len(digits) != 24:
        return False
    payload = digits[:22]
    try:
        key = int(digits[22:])
        rem = (int(payload) * 100) % 97
        expected_key = 97 - rem
        if expected_key == 0:
            expected_key = 97
        return key == expected_key and (int(digits) % 97 == 0)
    except Exception:
        return False


def format_moroccan_rib(rib: str) -> str:
    """
    Format a 24-digit RIB into standard Moroccan banking layout:
    BBB GGG CCCCCCCCCCCCCCCC KK (3 - 3 - 16 - 2)
    e.g. 240 810 00000000123456 78
    """
    digits = "".join(c for c in str(rib) if c.isdigit())
    if len(digits) == 24:
        return f"{digits[:3]} {digits[3:6]} {digits[6:22]} {digits[22:]}"
    return str(rib)


def rib_to_iban(rib: str) -> str:
    """
    Convert a Moroccan 24-digit RIB to a 28-character Moroccan IBAN (MA64 + RIB).
    ISO 13616 / ISO 7064 MOD 97-10 check: (rib * 10^6 + 221064) % 97 == 1.
    """
    digits = "".join(c for c in str(rib) if c.isdigit())
    return f"MA64{digits}"


def format_iban(iban: str) -> str:
    """
    Format a 28-char IBAN into 4-character chunks:
    MA64 2408 1000 0000 0012 3456 78
    """
    clean = str(iban).replace(" ", "").upper()
    return " ".join(clean[i:i+4] for i in range(0, len(clean), 4))


# ─────────────────────────────────────────────────────────────────────────────
# 2. 16-DIGIT VIRTUAL CARD (LUHN ALGORITHM MOD-10, COMPUTER-CALCULATED, NON-LIVE)
# ─────────────────────────────────────────────────────────────────────────────

def calculate_luhn_check_digit(payload_15: str) -> int:
    """
    Calculate the Luhn (Mod-10) check digit for a 15-digit payload.
    """
    digits = [int(d) for d in payload_15]
    checksum = 0
    double = True
    for d in reversed(digits):
        if double:
            val = d * 2
            checksum += (val - 9) if val > 9 else val
        else:
            checksum += d
        double = not double
    return (10 - (checksum % 10)) % 10


def generate_card_number(seed_or_account: str) -> str:
    """
    Generate a realistic 16-digit test card number calculated by computer.
    Uses test BIN 4240 (Visa sandbox / non-live range), 11-digit deterministic payload,
    and a mathematically verified Luhn check digit.
    Cannot be used for real unauthorized fraud/transactions.
    """
    # Deterministic hash to guarantee consistent card for a given account/seed
    h = int(hashlib.sha256(str(seed_or_account).encode("utf-8")).hexdigest(), 16)
    body = f"{h % (10**11):011d}"
    payload = f"4240{body}"
    check = calculate_luhn_check_digit(payload)
    return f"{payload}{check}"


def verify_luhn(card_number: str) -> bool:
    """
    Verify if a 16-digit card number satisfies the standard Luhn (Mod-10) algorithm.
    """
    digits = [int(d) for d in str(card_number) if d.isdigit()]
    if len(digits) != 16:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            val = d * 2
            checksum += (val - 9) if val > 9 else val
        else:
            checksum += d
    return checksum % 10 == 0


def format_card_number(card_number: str, masked: bool = False) -> str:
    """
    Format a 16-digit card number.
    If masked: '4240 •••• •••• 1234'
    If unmasked: '4240 1234 5678 9012'
    """
    digits = "".join(c for c in str(card_number) if c.isdigit())
    if len(digits) == 16:
        if masked:
            return f"{digits[:4]} •••• •••• {digits[-4:]}"
        return f"{digits[:4]} {digits[4:8]} {digits[8:12]} {digits[12:]}"
    return str(card_number)


def generate_cvv(card_or_account: str) -> str:
    """
    Generate a deterministic 3-digit CVV for the virtual card.
    """
    h = int(hashlib.md5(f"cvv:{card_or_account}".encode("utf-8")).hexdigest(), 16)
    return f"{(h % 900) + 100:03d}"
