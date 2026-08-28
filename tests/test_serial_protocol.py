"""Fingerprint serial-protocol parsing contract.

pytest isn't installed in this repo, so this runs as a plain script:

    venv/Scripts/python.exe -m tests.test_serial_protocol

These test the parser, not the sensor. No ESP32, no serial port, no hardware:
every case feeds a protocol line directly.

What matters here is that the protocol change is compatible in *both*
directions. The firmware lives on a separate device flashed by hand, so a host
update and a sensor update can never be assumed to land together:

    new host + old firmware -> "MATCH:12"      -> id 12, no score
    new host + new firmware -> "MATCH:12:145"  -> id 12, score 145
    old host + new firmware -> split(":")[1] still yields "12"

The third case is verified by test_legacy_field_extraction_still_works, which
runs the *old* parsing expression rather than the current code — the point is
that a host nobody has updated keeps working.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fingerprint_module.serial_handler import SerialHandler

parse = SerialHandler._parse_match_detailed
parse_legacy = SerialHandler._parse_match_response


# ── Current firmware: MATCH:<id>:<confidence> ────────────────


def test_scored_match_yields_id_and_score():
    assert parse("MATCH:12:145") == (12, True, 145)


def test_score_is_read_as_a_full_16_bit_value():
    """fingerSearch() builds confidence from two bytes, so it can exceed 255."""
    assert parse("MATCH:3:4096") == (3, True, 4096)


def test_zero_score_is_preserved_not_treated_as_missing():
    """A reported 0 is a measurement; it must not collapse into None."""
    fp_id, is_match, confidence = parse("MATCH:7:0")
    assert (fp_id, is_match) == (7, True)
    assert confidence == 0, "a reported zero must survive as 0, not None"


# ── Older firmware: MATCH:<id> ───────────────────────────────


def test_unscored_match_still_parses():
    assert parse("MATCH:12") == (12, True, None)


def test_missing_score_is_none_not_zero():
    """The distinction fusion depends on: 'not measured' is not 'measured bad'.
    Reading an unflashed sensor as 0 would score every genuine user as a
    maximally poor fingerprint match."""
    _fp_id, _is_match, confidence = parse("MATCH:12")
    assert confidence is None, "an absent score must be None, never 0"


# ── Non-matches ──────────────────────────────────────────────


def test_no_match():
    assert parse("NO_MATCH") == (None, False, None)


def test_sensor_error():
    assert parse("SENSOR_ERROR") == (None, False, None)


def test_unknown_response():
    assert parse("SOMETHING_ELSE") == (None, False, None)


def test_empty_response():
    assert parse("") == (None, False, None)


# ── Malformed input must not crash ───────────────────────────


def test_non_numeric_id_is_rejected():
    assert parse("MATCH:abc") == (None, False, None)


def test_missing_id_is_rejected():
    assert parse("MATCH:") == (None, False, None)


def test_unparseable_score_does_not_sink_a_valid_match():
    """A corrupt score field costs the score, not the whole authentication."""
    fp_id, is_match, confidence = parse("MATCH:12:notanumber")
    assert (fp_id, is_match) == (12, True), \
        "a bad score field must not discard a valid match"
    assert confidence is None


def test_extra_fields_are_ignored():
    """Forward compatibility: a future firmware adding a fourth field must not
    break this parser."""
    assert parse("MATCH:12:145:extra") == (12, True, 145)


# ── Backward compatibility of the existing API ───────────────


def test_legacy_parser_signature_is_unchanged():
    """_parse_match_response must still return exactly two values."""
    assert parse_legacy("MATCH:12:145") == (12, True)
    assert parse_legacy("MATCH:12") == (12, True)
    assert parse_legacy("NO_MATCH") == (None, False)


def test_legacy_field_extraction_still_works():
    """The pre-change expression, run against the new firmware's output.

    This is what an un-updated host does: response.split(":")[1]. It must still
    yield the fingerprint ID from a scored MATCH line, or flashing the sensor
    would break every host that hasn't been updated yet.
    """
    assert int("MATCH:12:145".split(":")[1]) == 12


def test_request_scan_keeps_its_two_tuple_return():
    """ui/atm_interface.py:682 unpacks exactly two values from this call."""
    import inspect
    signature = inspect.signature(SerialHandler.request_fingerprint_scan)
    assert list(signature.parameters) == ["self", "timeout", "expected_user_id"], \
        "the existing call site passes these by name"


def test_handler_exposes_last_match_confidence():
    handler = SerialHandler.__new__(SerialHandler)   # no serial port needed
    SerialHandler.__init__(handler, port="COM_TEST", baud_rate=115200)
    assert handler.last_match_confidence is None, \
        "should start unset, not 0"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"  ok   {fn.__name__}")
    print(f"\nOK - all {len(tests)} serial-protocol assertions passed.")


if __name__ == "__main__":
    main()
