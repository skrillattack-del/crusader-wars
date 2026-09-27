"""Crusader Wars 2 options ledger: load, validate, checksum.

cw2_config.json is the one ledger; schemas/config.schema.json is its contract.
Validation is a small JSON-Schema-subset interpreter so the schema file stays the
single source of truth without adding a dependency (the launcher is stdlib-only).
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

LEDGER_NAME = 'cw2_config.json'
LEDGER_DIR = 'config'
SCHEMA_NAME = 'config.schema.json'
SCHEMA_DIR = 'schemas'
REGISTRY_NAME = 'slots.registry.json'
SNAPSHOT_NAME = 'cw2_config.snapshot.json'

_TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool,
          'integer': int, 'number': (int, float), 'null': type(None)}


def validate(schema, doc, where='$'):
    """Validate doc against a JSON-Schema subset; raise ValueError with every violation.

    Supported: type, enum, properties, required, additionalProperties,
    minimum, exclusiveMinimum, maximum, exclusiveMaximum, default (used by
    with_defaults, not checked here).
    """
    errors = []
    _check(schema, doc, where, errors)
    if errors:
        raise ValueError('Invalid config: ' + '; '.join(errors))
    return doc


def _check(schema, doc, where, errors):
    expected = schema.get('type')
    if expected:
        py = _TYPES[expected]
        # bool is an int subclass; JSON 'integer'/'number' must not accept True/False.
        if expected in ('integer', 'number') and isinstance(doc, bool):
            errors.append(f'{where}: expected {expected}, got boolean')
            return
        if not isinstance(doc, py):
            errors.append(f'{where}: expected {expected}, got {type(doc).__name__}')
            return
    if 'enum' in schema and doc not in schema['enum']:
        errors.append(f"{where}: {doc!r} is not one of {schema['enum']}")
    if isinstance(doc, bool):
        return  # the remaining keywords compare orderable non-booleans
    if 'minimum' in schema and doc < schema['minimum']:
        errors.append(f'{where}: {doc} < minimum {schema["minimum"]}')
    if 'exclusiveMinimum' in schema and doc <= schema['exclusiveMinimum']:
        errors.append(f'{where}: {doc} <= exclusiveMinimum {schema["exclusiveMinimum"]}')
    if 'maximum' in schema and doc > schema['maximum']:
        errors.append(f'{where}: {doc} > maximum {schema["maximum"]}')
    if 'exclusiveMaximum' in schema and doc >= schema['exclusiveMaximum']:
        errors.append(f'{where}: {doc} >= exclusiveMaximum {schema["exclusiveMaximum"]}')
    if isinstance(doc, dict):
        props = schema.get('properties', {})
        for key in schema.get('required', []):
            if key not in doc:
                errors.append(f'{where}.{key}: missing (required)')
        if schema.get('additionalProperties') is False:
            for key in doc:
                if key not in props:
                    errors.append(f'{where}.{key}: unknown key')
        for key, sub in props.items():
            if key in doc:
                _check(sub, doc[key], f'{where}.{key}', errors)


def with_defaults(schema):
    """A fresh document holding every property's declared default."""
    return {key: sub.get('default') for key, sub in schema.get('properties', {}).items()
            if 'default' in sub}


def effective(schema, doc):
    """Schema defaults overlaid with the document's values, then validated."""
    merged = with_defaults(schema)
    merged.update(doc or {})
    return validate(schema, merged)


def checksum(doc):
    """SHA-256 of the canonical JSON (sorted keys, compact separators)."""
    blob = json.dumps(doc, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def checksum_file(path):
    return checksum(json.loads(Path(path).read_text(encoding='utf-8')))


def _find_upwards(start, dirname, filename):
    """dir/filename in start or any parent, mirroring Bridge._find_cli."""
    for folder in (Path(start), *Path(start).parents):
        candidate = folder / dirname / filename
        if candidate.is_file():
            return candidate
    return None


def find_ledger(base):
    """The ledger path: config/cw2_config.json found upwards from base, or seeded
    with defaults beside base on first run."""
    found = _find_upwards(base, LEDGER_DIR, LEDGER_NAME)
    if found:
        return found
    ledger = Path(base) / LEDGER_DIR / LEDGER_NAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    schema = find_schema(base)
    defaults = with_defaults(json.loads(schema.read_text(encoding='utf-8'))) if schema else {}
    ledger.write_text(json.dumps(defaults, indent=2) + '\n', encoding='utf-8')
    return ledger


def find_schema(base):
    return _find_upwards(base, SCHEMA_DIR, SCHEMA_NAME)


def find_registry(base):
    return _find_upwards(base, LEDGER_DIR, REGISTRY_NAME)


def load(base):
    """(config, path, sha256). Raises ValueError when the ledger breaks the schema."""
    schema_path = find_schema(base)
    if not schema_path:
        raise ValueError(f'{SCHEMA_DIR}/{SCHEMA_NAME} not found above {base}.')
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    ledger = find_ledger(base)
    try:
        doc = json.loads(ledger.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise ValueError(f'{ledger} is not valid JSON: {exc}') from exc
    config = effective(schema, doc)
    return config, ledger, checksum(config)


def save(base, patch):
    """Merge patch onto the effective config, validate, atomically write back.

    Returns (config, path, sha256). The on-disk file holds the full effective
    config; defaults are refreshed from the schema on every load anyway.
    """
    schema = json.loads(find_schema(base).read_text(encoding='utf-8'))
    current = effective(schema, _read_json(find_ledger(base)))
    if not isinstance(patch, dict):
        raise ValueError('Config patch must be an object.')
    merged = dict(current)
    merged.update(patch)
    config = validate(schema, merged)
    ledger = find_ledger(base)
    tmp = ledger.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    tmp.replace(ledger)
    return config, ledger, checksum(config)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return {}


def assert_injective(registry, strict=True):
    """ck3_character_id <-> cw2 slot bijection over config/slots.registry.json.

    strict: raise on the first collision. Not strict: return the violation list
    (empty when clean). An empty registry is trivially injective.
    """
    mappings = (registry or {}).get('mappings', [])
    seen_chars, seen_slots, violations = {}, {}, []
    for row in mappings:
        char, slot = row.get('ck3_character_id'), row.get('slot')
        if char in seen_chars:
            violations.append(f'character {char} maps to both {seen_chars[char]!r} and {slot!r}')
        if slot in seen_slots:
            violations.append(f'slot {slot!r} is taken by both character {seen_slots[slot]} and {char}')
        seen_chars[char] = slot
        seen_slots[slot] = char
    if violations and strict:
        raise ValueError('config/slots.registry.json is not injective: ' + '; '.join(violations))
    return violations


def check_slots(base, strict=True):
    """Injectivity rail over the discovered registry; (violations, registry_path|None)."""
    path = find_registry(base)
    if not path:
        return [], None
    try:
        registry = json.loads(path.read_text(encoding='utf-8'))
    except ValueError as exc:
        raise ValueError(f'{path} is not valid JSON: {exc}') from exc
    return assert_injective(registry, strict=strict), path


def maybe_request_screenshots(run_dir, enabled):
    """Screenshot seam: record the request in the run folder. No capture backend
    exists yet; when one lands it replaces this body and the config plumbing is
    already in place. Returns the flag path when requested, else None."""
    if not enabled:
        return None
    run = Path(run_dir)
    run.mkdir(parents=True, exist_ok=True)
    flag = run / 'screenshots_requested.flag'
    flag.write_text('enable_tw3k_screenshots is on, but no capture backend exists yet.\n',
                    encoding='utf-8')
    return flag
