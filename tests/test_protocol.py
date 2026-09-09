from common.crypto import sha256_hex
from common.models import SessionStatus
from common.protocol import InputCommand, SignalEnvelope


def test_pairing_hash_is_one_way_value() -> None:
    assert sha256_hex("482-913") == sha256_hex("482-913")
    assert sha256_hex("482-913") != sha256_hex("482-914")


def test_protocol_models_accept_control_messages() -> None:
    message = SignalEnvelope(type="offer", session_id="session-1", payload={"sdp": "demo"})
    command = InputCommand(type="mouse_move", x=10, y=20)
    assert message.session_id == "session-1"
    assert command.x == 10
    assert SessionStatus.ACTIVE.value == "active"

