"""
Tests for VoucherManager — pure logic, no hardware or real DB required.
FakeVoucherDB mimics the voucher methods added to database/db_manager.py
(create_voucher / get_active_vouchers / apply_vouchers) plus the settings
helpers, in the same spirit as FakeDBManager in test_session_manager.py.
"""
from datetime import datetime, timedelta

import pytest

import managers.voucher_manager as vm
from managers.voucher_manager import (
    CODE_ALPHABET,
    MAX_FAILED_ATTEMPTS,
    LookupStatus,
    VoucherManager,
    format_code,
    normalize_code,
)


class FakeVoucherDB:
    def __init__(self, settings=None):
        self.settings = dict(settings or {})
        self.vouchers = {}       # voucher_id -> row dict
        self.applications = []   # rows of voucher_applications
        self.fail_create = False
        self.fail_apply = False

    def get_setting(self, key, default=None):
        value = self.settings.get(key, default)
        # real get_setting returns int for int-like text, else the string
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    def update_setting(self, key, value):
        self.settings[key] = str(value)

    def create_voucher(self, voucher_id, code_hash, value, created_at, expires_at, payment_ref=None):
        if self.fail_create:
            return False
        self.vouchers[voucher_id] = {
            'voucher_id': voucher_id,
            'code_hash': code_hash,
            'initial_value': value,
            'remaining_value': value,
            'created_at': created_at,
            'expires_at': expires_at,
            'payment_ref': payment_ref,
        }
        return True

    def get_active_vouchers(self, now):
        return [
            dict(v) for v in self.vouchers.values()
            if v['remaining_value'] > 0 and v['expires_at'] > now
        ]

    def get_inactive_vouchers(self, now):
        return [
            dict(v) for v in self.vouchers.values()
            if v['remaining_value'] <= 0 or v['expires_at'] <= now
        ]

    def apply_vouchers(self, plan, payment_ref, applied_at):
        if self.fail_apply:
            return False
        # all-or-nothing, like the real single-transaction implementation
        for voucher_id, amount in plan:
            v = self.vouchers.get(voucher_id)
            if v is None or v['remaining_value'] < amount or v['expires_at'] <= applied_at:
                return False
        for voucher_id, amount in plan:
            self.vouchers[voucher_id]['remaining_value'] -= amount
            self.applications.append({
                'voucher_id': voucher_id, 'amount': amount,
                'payment_ref': payment_ref, 'applied_at': applied_at,
            })
        return True


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 12, 0, 0)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def db():
    return FakeVoucherDB()


@pytest.fixture
def manager(db, clock, monkeypatch):
    monkeypatch.setattr(vm, '_generate_qr_bytes', lambda payload: payload.encode())
    return VoucherManager(db, now_fn=clock)


class TestCodeFormat:
    def test_alphabet_is_crockford_base32(self):
        assert len(CODE_ALPHABET) == 32
        assert not set("ILOU") & set(CODE_ALPHABET)

    def test_normalize_accepts_typed_forms(self):
        assert normalize_code("abcd-1234") == "ABCD1234"
        assert normalize_code(" ABCD 1234 ") == "ABCD1234"
        assert normalize_code("V1:ABCD1234") == "ABCD1234"

    def test_normalize_fixes_lookalikes(self):
        assert normalize_code("ABCDO1IL") == "ABCD0111"

    @pytest.mark.parametrize("bad", ["", "ABC", "ABCD12345", "ABCU1234", "ABC!1234", None, 12345678])
    def test_normalize_rejects_non_codes(self, bad):
        assert normalize_code(bad) is None

    def test_format_code(self):
        assert format_code("ABCD1234") == "ABCD-1234"


class TestIssue:
    def test_issues_code_value_and_qr(self, manager):
        v = manager.issue(7)
        assert v.value == 7
        assert len(v.code) == 8 and set(v.code) <= set(CODE_ALPHABET)
        assert v.display_code == f"{v.code[:4]}-{v.code[4:]}"
        assert v.qr_bytes == f"V1:{v.code}".encode()

    def test_default_expiry_is_30_days(self, manager, clock):
        v = manager.issue(5)
        assert v.expires_at == clock.now + timedelta(days=30)

    def test_expiry_is_configurable(self, db, clock, monkeypatch):
        monkeypatch.setattr(vm, '_generate_qr_bytes', lambda p: b'')
        m = VoucherManager(FakeVoucherDB({'voucher_expiry_days': 7}), now_fn=clock)
        assert m.issue(5).expires_at == clock.now + timedelta(days=7)

    def test_db_stores_only_a_salted_hash(self, manager, db):
        v = manager.issue(5)
        row = db.vouchers[v.voucher_id]
        assert v.code not in str(row)
        assert row['code_hash'] == vm._hash_code(v.voucher_id, v.code)

    def test_same_code_hashes_differently_per_voucher(self):
        assert vm._hash_code("a" * 16, "ABCD1234") != vm._hash_code("b" * 16, "ABCD1234")

    @pytest.mark.parametrize("bad", [0, -3, 0.2])
    def test_non_positive_shortfall_rejected(self, manager, bad):
        with pytest.raises(ValueError):
            manager.issue(bad)

    def test_persist_failure_raises_and_leaves_no_voucher(self, manager, db):
        db.fail_create = True
        with pytest.raises(RuntimeError):
            manager.issue(5)
        assert db.vouchers == {}

    def test_qr_failure_still_returns_typeable_code(self, manager, db, monkeypatch):
        def boom(payload):
            raise OSError("qr broke")
        monkeypatch.setattr(vm, '_generate_qr_bytes', boom)
        v = manager.issue(5)
        assert v.qr_bytes is None
        assert v.voucher_id in db.vouchers  # already persisted

    def test_payment_ref_is_recorded(self, manager, db):
        v = manager.issue(5, payment_ref="pay123")
        assert db.vouchers[v.voucher_id]['payment_ref'] == "pay123"


class TestBalance:
    def test_returns_remaining_and_expiry(self, manager):
        v = manager.issue(9)
        r = manager.balance(v.display_code)
        assert r.success and r.remaining == 9
        assert r.expires_at == v.expires_at

    def test_unknown_code_fails(self, manager):
        manager.issue(9)
        r = manager.balance("ZZZZ-ZZZZ")
        assert not r.success and not r.locked

    def test_malformed_input_does_not_count_toward_lockout(self, manager, db):
        for _ in range(MAX_FAILED_ATTEMPTS + 2):
            assert not manager.balance("nope").success
        assert int(db.get_setting('voucher_failed_attempts', 0)) == 0

    def test_expired_voucher_is_not_found(self, manager, clock):
        v = manager.issue(9)
        clock.advance(days=30, seconds=1)
        assert not manager.balance(v.code).success

    def test_qr_payload_form_is_accepted(self, manager):
        v = manager.issue(9)
        assert manager.balance(f"V1:{v.code}").success


class TestDistinctOutcomes:
    def test_unknown_code(self, manager):
        r = manager.balance("ZZZZ-ZZZZ")
        assert r.status == LookupStatus.UNKNOWN
        assert "recognise" in r.message

    def test_expired_code_names_its_expiry_and_is_not_a_wrong_guess(self, manager, clock, db):
        v = manager.issue(9)
        clock.advance(days=31)
        r = manager.balance(v.code)
        assert (r.success, r.status) == (False, LookupStatus.EXPIRED)
        assert "expired" in r.message and str(v.expires_at.year) in r.message
        assert int(db.get_setting('voucher_failed_attempts', 0)) == 0

    def test_fully_used_code_is_not_a_wrong_guess(self, manager, db):
        v = manager.issue(5)
        manager.apply([v.code], 5)
        r = manager.balance(v.code)
        assert (r.success, r.status) == (False, LookupStatus.USED)
        assert "fully used" in r.message
        assert int(db.get_setting('voucher_failed_attempts', 0)) == 0

    def test_messages_are_all_different(self, manager, clock):
        used, expired = manager.issue(5), manager.issue(5)
        manager.apply([used.code], 5)
        clock.advance(days=31)
        messages = {manager.balance(c).message for c in (used.code, expired.code, "ZZZZZZZZ", "nope")}
        assert len(messages) == 4

    def test_apply_reports_the_failing_status(self, manager):
        v = manager.issue(5)
        manager.apply([v.code], 5)
        assert manager.apply([v.code], 5).status == LookupStatus.USED

    def test_locked_status(self, manager):
        for _ in range(MAX_FAILED_ATTEMPTS):
            r = manager.balance("ZZZZZZZZ")
        assert r.status == LookupStatus.LOCKED
        assert "minute" in r.message


class TestLockout:
    def test_five_wrong_codes_lock_even_the_right_code(self, manager):
        v = manager.issue(9)
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            assert not manager.balance("ZZZZZZZZ").locked
        assert manager.balance("ZZZZZZZZ").locked  # the 5th trips it
        r = manager.balance(v.code)
        assert not r.success and r.locked

    def test_lockout_expires(self, manager, clock):
        v = manager.issue(9)
        for _ in range(MAX_FAILED_ATTEMPTS):
            manager.balance("ZZZZZZZZ")
        clock.advance(minutes=5, seconds=1)
        assert manager.balance(v.code).success

    def test_counter_is_shared_between_balance_and_apply(self, manager):
        v = manager.issue(9)
        for _ in range(3):
            manager.balance("ZZZZZZZZ")
        for _ in range(MAX_FAILED_ATTEMPTS - 3 - 1):
            manager.apply(["ZZZZZZZZ"], 5)
        assert manager.apply(["ZZZZZZZZ"], 5).locked
        assert manager.apply([v.code], 5).locked

    def test_success_resets_the_counter(self, manager, db):
        v = manager.issue(9)
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            manager.balance("ZZZZZZZZ")
        assert manager.balance(v.code).success
        assert int(db.get_setting('voucher_failed_attempts', 0)) == 0
        # a fresh run of misses is needed to lock again
        for _ in range(MAX_FAILED_ATTEMPTS - 1):
            assert not manager.balance("ZZZZZZZZ").locked

    def test_lockout_duration_is_configurable(self, clock, monkeypatch):
        monkeypatch.setattr(vm, '_generate_qr_bytes', lambda p: b'')
        m = VoucherManager(FakeVoucherDB({'voucher_lockout_minutes': 1}), now_fn=clock)
        v = m.issue(9)
        for _ in range(MAX_FAILED_ATTEMPTS):
            m.balance("ZZZZZZZZ")
        clock.advance(seconds=61)
        assert m.balance(v.code).success


class TestApply:
    def test_partial_use_keeps_same_code_and_expiry(self, manager, db):
        v = manager.issue(10)
        r = manager.apply([v.code], 4, payment_ref="p1")
        assert r.success and r.total_applied == 4
        assert r.applications == [{"voucher_id": v.voucher_id, "amount": 4, "remaining": 6}]
        assert db.vouchers[v.voucher_id]['expires_at'] == v.expires_at  # never extended
        # the same code still works for the remainder
        assert manager.balance(v.code).remaining == 6
        assert manager.apply([v.code], 6).total_applied == 6
        assert not manager.balance(v.code).success  # fully used

    def test_application_is_linked_to_the_payment(self, manager, db):
        v = manager.issue(10)
        manager.apply([v.code], 4, payment_ref="pay-xyz")
        assert db.applications[0]['payment_ref'] == "pay-xyz"
        assert db.applications[0]['voucher_id'] == v.voucher_id

    def test_several_vouchers_used_in_entry_order_last_is_partial(self, manager):
        a, b, c = manager.issue(3), manager.issue(4), manager.issue(10)
        r = manager.apply([a.code, b.code, c.code], 10)
        assert r.total_applied == 10
        assert [x["amount"] for x in r.applications] == [3, 4, 3]
        assert [x["remaining"] for x in r.applications] == [0, 0, 7]

    def test_vouchers_beyond_the_amount_are_left_untouched(self, manager, db):
        a, b = manager.issue(10), manager.issue(10)
        r = manager.apply([a.code, b.code], 6)
        assert [x["voucher_id"] for x in r.applications] == [a.voucher_id]
        assert db.vouchers[b.voucher_id]['remaining_value'] == 10

    def test_insufficient_voucher_is_still_a_success_with_the_rest_in_cash(self, manager):
        v = manager.issue(4)
        r = manager.apply([v.code], 10)
        assert r.success and r.total_applied == 4

    def test_duplicate_code_is_applied_once(self, manager, db):
        v = manager.issue(10)
        r = manager.apply([v.code, v.display_code], 8)
        assert r.total_applied == 8
        assert len(r.applications) == 1
        assert db.vouchers[v.voucher_id]['remaining_value'] == 2

    def test_one_bad_code_applies_nothing(self, manager, db):
        v = manager.issue(10)
        r = manager.apply([v.code, "ZZZZZZZZ"], 5)
        assert not r.success
        assert db.vouchers[v.voucher_id]['remaining_value'] == 10
        assert db.applications == []

    def test_expired_voucher_cannot_be_applied(self, manager, clock):
        v = manager.issue(10)
        clock.advance(days=31)
        assert not manager.apply([v.code], 5).success

    def test_db_failure_reports_failure_and_changes_nothing(self, manager, db):
        v = manager.issue(10)
        db.fail_apply = True
        r = manager.apply([v.code], 5)
        assert not r.success
        assert db.vouchers[v.voucher_id]['remaining_value'] == 10

    @pytest.mark.parametrize("due", [0, -5])
    def test_nothing_due_is_a_noop(self, manager, db, due):
        v = manager.issue(10)
        r = manager.apply([v.code], due)
        assert r.success and r.total_applied == 0
        assert db.vouchers[v.voucher_id]['remaining_value'] == 10

    def test_no_codes_is_a_noop(self, manager):
        assert manager.apply([], 10).total_applied == 0