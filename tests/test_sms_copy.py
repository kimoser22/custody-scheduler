"""Carrier / brand phrases in outbound SMS keyword replies."""

from concierge.sms_copy import (
    HELP_REPLY,
    OPT_IN_REPLY,
    OPT_OUT_REPLY,
    PROGRAM_NAME,
    STILL_OPTED_OUT_REPLY,
)


def test_sms_copy_names_program() -> None:
    assert PROGRAM_NAME == "Moser Custody Concierge"
    assert PROGRAM_NAME in OPT_OUT_REPLY
    assert PROGRAM_NAME in HELP_REPLY
    assert PROGRAM_NAME in OPT_IN_REPLY
    assert PROGRAM_NAME in STILL_OPTED_OUT_REPLY


def test_sms_copy_includes_stop_help_and_rates() -> None:
    assert "STOP" in HELP_REPLY
    assert "HELP" in OPT_OUT_REPLY or "help" in OPT_OUT_REPLY.lower()
    assert "START" in OPT_OUT_REPLY
    assert "Msg & data rates may apply" in HELP_REPLY or (
        "message and data rates may apply" in HELP_REPLY.lower()
    )
    assert "Message frequency varies" in HELP_REPLY
