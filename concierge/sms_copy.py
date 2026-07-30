"""User-facing SMS copy for the Moser Custody Concierge program."""

PROGRAM_NAME = "Moser Custody Concierge"

OPT_OUT_REPLY = (
    f"You have opted out of {PROGRAM_NAME} messages. "
    "No further scheduling texts will be sent to this number. "
    "Reply START to opt back in. Reply HELP for help."
)

HELP_REPLY = (
    f"{PROGRAM_NAME}: private household scheduling texts. "
    "Message frequency varies. Msg & data rates may apply. "
    "Reply STOP to opt out. Reply START to opt back in after STOP."
)

OPT_IN_REPLY = (
    f"You are opted in to {PROGRAM_NAME} messages again. "
    "Reply STOP to opt out anytime."
)

STILL_OPTED_OUT_REPLY = (
    f"You are opted out of {PROGRAM_NAME} messages. "
    "Reply START to receive scheduling texts again."
)
