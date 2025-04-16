import re

def clean_string(s):
    return re.sub(r'[^a-zA-Z0-9 ]+', '', s)


def to_snake_case(s):
    # Replace spaces and hyphens with underscores
    s = re.sub(r"[ -]+", "_", s)
    # Add underscore between camelCase or PascalCase
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    # Lowercase and remove any accidental double underscores
    s = s.lower()
    s = re.sub(r"__+", "_", s)
    return s.strip("_")


def snake_case_keys(obj):
    if isinstance(obj, dict):
        return {to_snake_case(k): snake_case_keys(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [snake_case_keys(i) for i in obj]
    else:
        return obj

def to_int(value, fallback=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return fallback

def to_float(value, fallback=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return fallback
