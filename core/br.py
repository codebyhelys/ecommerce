def normalize_zip_code(value):
    """'01310100' ou '01310-100' -> '01310-100'. Levanta ValueError se não tiver 8 dígitos."""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) != 8:
        raise ValueError("CEP deve ter 8 dígitos.")
    return f"{digits[:5]}-{digits[5:]}"


def normalize_state(value):
    """'sp' -> 'SP'. Levanta ValueError se não forem 2 letras."""
    value = str(value).strip().upper()
    if len(value) != 2 or not value.isalpha():
        raise ValueError("Informe a sigla do estado com 2 letras.")
    return value
