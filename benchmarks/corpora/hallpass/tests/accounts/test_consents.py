from hallpass.accounts import consents, residents


def test_sms_reminders_off_without_a_row(pg_conn, make_resident):
    rid = make_resident(phone="+447700900001")
    assert consents.current(pg_conn, rid, "sms_reminders") is False


def test_email_reminders_on_without_a_row(pg_conn, make_resident):
    assert consents.current(pg_conn, make_resident(), "email_reminders") is True


def test_register_with_box_ticked_records_consent(pg_conn, frozen):
    rid = residents.register(pg_conn, email="new@example.org", full_name="Nia Patel",
                             phone="07700 900456", sms_reminders=True)
    assert consents.current(pg_conn, rid, "sms_reminders") is True
    (source,) = pg_conn.execute(
        "SELECT source FROM consents WHERE resident_id = %s", (rid,)
    ).fetchone()
    assert source == "signup_form"


def test_register_without_box_writes_no_row(pg_conn, frozen):
    rid = residents.register(pg_conn, email="quiet@example.org", full_name="Quiet Person",
                             phone="07700900457")
    (n,) = pg_conn.execute("SELECT count(*) FROM consents WHERE resident_id = %s", (rid,)).fetchone()
    assert n == 0


def test_latest_decision_wins_in_bulk_lookup(pg_conn, frozen, make_resident):
    a, b, c = (make_resident(f"{x}@example.org") for x in "abc")
    consents.record(pg_conn, b, "sms_reminders", True, source="account_page")
    consents.record(pg_conn, c, "sms_reminders", True, source="import")
    consents.record(pg_conn, c, "sms_reminders", False, source="sms_stop")
    assert consents.sms_opted_in(pg_conn, [a, b, c]) == {b}
