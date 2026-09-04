"""Standalone self-check for the v3.5 (0x6699/GCM) wire format added to
custom_components/localtuya/pytuya/__init__.py - round-trips pack_message ->
unpack_message and asserts the payload, seqno, cmd and retcode all survive
intact. Does not touch a real device; run with:
    python3 tests/test_v35_roundtrip.py
"""
import os
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", "custom_components", "localtuya", "pytuya"
    ),
)

from __init__ import (  # noqa: E402
    CONTROL_NEW,
    DP_QUERY_NEW,
    PREFIX_6699_VALUE,
    TuyaMessage,
    pack_message,
    parse_header,
    unpack_message,
)


class _NullLogger:
    def debug(self, *a, **k):
        pass


def roundtrip(cmd, payload, retcode, key):
    out_msg = TuyaMessage(42, cmd, retcode, payload, 0, True, PREFIX_6699_VALUE, True)
    wire = pack_message(out_msg, hmac_key=key)

    header = parse_header(wire)
    assert header.prefix == PREFIX_6699_VALUE
    assert header.seqno == 42
    assert header.cmd == cmd
    assert header.total_length == len(wire), (header.total_length, len(wire))

    parsed = unpack_message(wire, hmac_key=key, header=header, logger=_NullLogger())
    assert parsed.crc_good, "GCM tag verification failed"
    assert parsed.payload == payload, (parsed.payload, payload)
    assert parsed.seqno == 42
    assert parsed.cmd == cmd
    return parsed


def demo():
    key = os.urandom(16)

    # Real usage only ever unpack_message()'s INCOMING (device -> client)
    # traffic, which always carries a retcode - client requests (retcode=
    # None when packing, see _encode_message) are sent, never unpacked.
    p = roundtrip(DP_QUERY_NEW, b'{"gwId":"","devId":"","uid":"","t":"1"}', 0, key)
    assert p.retcode == 0

    p2 = roundtrip(CONTROL_NEW, b'{"dps":{"1":true}}', 0, key)
    assert p2.retcode == 0

    # packing WITHOUT a retcode (the outgoing-request shape) must omit the
    # 4 retcode bytes, not just leave them zeroed
    with_retcode = pack_message(
        TuyaMessage(1, DP_QUERY_NEW, 0, b"{}", 0, True, PREFIX_6699_VALUE, True), hmac_key=key
    )
    without_retcode = pack_message(
        TuyaMessage(1, DP_QUERY_NEW, None, b"{}", 0, True, PREFIX_6699_VALUE, True), hmac_key=key
    )
    assert len(without_retcode) == len(with_retcode) - 4, (
        len(without_retcode), len(with_retcode)
    )

    # wrong key must fail the GCM tag check, not silently decode garbage
    out_msg = TuyaMessage(1, DP_QUERY_NEW, None, b"{}", 0, True, PREFIX_6699_VALUE, True)
    wire = pack_message(out_msg, hmac_key=key)
    bad = unpack_message(wire, hmac_key=os.urandom(16), logger=_NullLogger())
    assert bad.crc_good is False

    print("v3.5 pack/unpack round-trip: OK")


if __name__ == "__main__":
    demo()
