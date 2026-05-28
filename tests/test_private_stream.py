from mexc_futures_engine.private_stream import classify_private_channel
from mexc_futures_engine.private_stream import parse_private_ws_message


def test_private_ack_message_to_control_event():
    event = parse_private_ws_message(
        {"channel": "rs.login", "data": "success", "ts": 1778733931773},
        ts_init_ms=1778733932000,
    ).to_dict(include_raw=False)

    assert event["eventType"] == "ControlAck"
    assert event["channel"] == "rs.login"
    assert event["payload"]["ok"] is True
    assert event["payload"]["method"] == "login"
    assert event["tsEventNs"] == 1778733931773000000
    assert "raw" not in event


def test_private_channel_classification():
    assert classify_private_channel("push.personal.account") == "AccountUpdate"
    assert classify_private_channel("push.personal.position") == "PositionUpdate"
    assert classify_private_channel("push.personal.order") == "OrderUpdate"
    assert classify_private_channel("push.personal.deal") == "FillUpdate"
    assert classify_private_channel("push.unknown") == "PrivateUpdate"
