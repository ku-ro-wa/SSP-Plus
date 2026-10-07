"""Tests for the voucher-issued screen's model (pure Python, no PyQt needed)."""
import locale
from datetime import datetime

import pytest

from managers.voucher_manager import IssuedVoucher
from screens.voucher.model import PESO, VoucherModel


def make_voucher(value=7, code="ABCD1234", qr=b"png", expires=datetime(2026, 10, 31, 9, 0)):
    return IssuedVoucher(
        voucher_id="v1", code=code, display_code=f"{code[:4]}-{code[4:]}",
        value=value, qr_bytes=qr, expires_at=expires,
    )


@pytest.fixture
def model():
    return VoucherModel()


class TestIssued:
    def test_copies_fields_and_reports_code(self, model):
        model.set_voucher(make_voucher())
        assert model.state == VoucherModel.ISSUED
        assert model.value == 7
        assert model.display_code == "ABCD-1234"
        assert model.has_code and model.has_qr

    def test_does_not_keep_the_raw_code_or_the_object(self, model):
        model.set_voucher(make_voucher(code="ZXCV5678"))
        assert "ZXCV5678" not in str(vars(model))

    def test_copy_mentions_amount_and_expiry_without_zero_padding(self, model):
        model.set_voucher(make_voucher(value=7, expires=datetime(2026, 11, 1)))
        assert f"{PESO}7" in model.body()
        assert "November 1, 2026" in model.footnote()

    def test_footnote_warns_the_code_is_shown_once(self, model):
        model.set_voucher(make_voucher())
        assert "only once" in model.footnote()

    def test_button_asks_for_acknowledgement(self, model):
        model.set_voucher(make_voucher())
        assert "saved" in model.button_text()

    def test_missing_qr_still_has_a_typeable_code(self, model):
        model.set_voucher(make_voucher(qr=None))
        assert model.has_code and not model.has_qr


class TestFailure:
    def test_failure_has_amount_but_no_code(self, model):
        model.set_failure(12)
        assert model.state == VoucherModel.FAILED
        assert model.value == 12
        assert not model.has_code and not model.has_qr

    def test_failure_copy_names_the_amount_and_the_attendant(self, model):
        model.set_failure(12)
        assert f"{PESO}12" in model.body()
        assert "attendant" in model.body()
        assert model.footnote() == ""
        assert model.button_text() == "Continue"

    def test_failure_after_an_issued_voucher_wipes_the_old_code(self, model):
        model.set_voucher(make_voucher())
        model.set_failure(5)
        assert model.display_code == "" and model.qr_bytes is None


class TestClear:
    def test_clear_wipes_everything(self, model):
        model.set_voucher(make_voucher())
        model.clear()
        assert model.state == VoucherModel.EMPTY
        assert model.value == 0
        assert model.display_code == ""
        assert model.qr_bytes is None
        assert model.expires_at is None
        assert not model.has_code


def test_expiry_month_is_english_whatever_the_locale():
    saved = locale.setlocale(locale.LC_TIME)
    try:
        try:
            locale.setlocale(locale.LC_TIME, "ja_JP.UTF-8")
        except locale.Error:
            pytest.skip("ja_JP locale not installed")
        model = VoucherModel()
        model.set_voucher(IssuedVoucher(voucher_id="v", code="ABCD1234", display_code="ABCD-1234",
                                        value=5, qr_bytes=None, expires_at=datetime(2026, 11, 1)))
        assert "November 1, 2026" in model.footnote()
    finally:
        locale.setlocale(locale.LC_TIME, saved)
