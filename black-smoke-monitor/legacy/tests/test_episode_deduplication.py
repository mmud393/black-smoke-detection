from smoke_monitor.verifier import EpisodeTracker

B = (10, 10, 60, 60)


def tracker():
    return EpisodeTracker(min_detections=3, min_span=3.0, clear_seconds=20.0)


def test_single_frame_never_alerts():
    t = tracker()
    assert t.update(0, B) is False and t.state == "SUSPECTED"


def test_three_frames_over_three_seconds_alert_once():
    t = tracker()
    res = [t.update(s, B) for s in (0, 1, 2, 3, 4, 5, 6)]
    assert res == [False, False, False, True, False, False, False]
    assert t.state == "ALERTED"


def test_fast_detections_below_span_do_not_alert():
    t = tracker()
    assert not any(t.update(s, B) for s in (0, 0.5, 1.0, 1.5))


def test_gap_resets_suspicion():
    t = tracker()
    t.update(0, B); t.update(1, B)
    t.update(10, B)  # gap > max_gap restarts the chain
    assert t.update(11, B) is False and t.state == "SUSPECTED"


def test_unrelated_location_resets_chain():
    t = tracker()
    t.update(0, B); t.update(1, B)
    assert t.update(2, (200, 200, 250, 250)) is False
    assert t.state == "SUSPECTED"


def test_short_dropout_does_not_rearm():
    t = tracker()
    for s in (0, 1, 2, 3):
        t.update(s, B)
    assert t.update(8, None) is False and t.state == "CLEARING"
    assert not any(t.update(s, B) for s in (9, 10, 11, 12))  # same episode


def test_clear_then_return_alerts_again():
    t = tracker()
    for s in (0, 1, 2, 3):
        t.update(s, B)
    for s in range(4, 30):
        t.update(s, None)
    assert t.state == "CLEAR"
    res = [t.update(s, B) for s in (40, 41, 42, 43)]
    assert res == [False, False, False, True]


def test_resume_after_restart_suppresses_duplicate():
    t = tracker()
    t.resume_alerted(100)
    assert not any(t.update(s, B) for s in range(100, 110))
