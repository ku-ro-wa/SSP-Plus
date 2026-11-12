"""
Marking errors resolved (issue #136): Dashboard (`/kiosk`, `/logs`), the touchscreen
data viewer and the thank-you screen's PIN override all mark the same error_log
row through managers/error_resolution.py, each writing an admin_actions row, and
the unresolved count is the same on both sides.
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from SSP.admin_dashboard.main import app  # noqa: E402
from admin_dashboard.cli import create_account  # noqa: E402
from admin_dashboard.dependencies import get_db  # noqa: E402
from database.db_manager import DatabaseManager  # noqa: E402
from database.models import init_db  # noqa: E402
from screens.data_viewer.controller import DataViewerController  # noqa: E402


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / 'resolved.db')
    init_db(path)
    return path


@pytest.fixture
def db(db_path):
    d = DatabaseManager(db_path=db_path)
    yield d
    d.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def login(client, db, role='admin', name='sam'):
    client.cookies.clear()
    create_account(db, name, 's3cret!', role)
    client.post('/login', json={'username': name, 'password': 's3cret!'})


def audit(db):
    rows, _ = db.get_admin_action_page(100)
    return [(r['actor'], r['location'], r['action'], r['old_value'], r['new_value']) for r in reversed(rows)]


def resolved(db, error_id):
    return bool(db.conn.execute('SELECT resolved FROM error_log WHERE id = ?', (error_id,)).fetchone()['resolved'])


class TestDashboard:
    def test_admin_marks_one_row_and_it_leaves_the_unresolved_list(self, client, db):
        a = db.log_error('Printing Error', 'jam', 'thank_you_screen')
        b = db.log_error('QR Reader', 'unplugged', 'qr')
        login(client, db)
        r = client.post(f'/errors/{a}/resolve')
        assert r.json() == {'resolved': True, 'changed': True, 'unresolved': 1}
        assert resolved(db, a) and not resolved(db, b)
        assert [e['id'] for e in client.get('/kiosk/data').json()['errors']] == [b]
        assert client.get('/kiosk/data').json()['error_total'] == 1
        assert audit(db) == [('sam', 'dashboard', 'error_resolved', f'#{a} Printing Error: jam', 'resolved')]
        assert db.get_admin_action_page(1)[0][0]['source_ip'] == 'testclient'

    def test_marking_again_changes_and_writes_nothing(self, client, db):
        a = db.log_error('E', 'm', 's')
        login(client, db)
        client.post(f'/errors/{a}/resolve')
        r = client.post(f'/errors/{a}/resolve')
        assert r.status_code == 200 and r.json()['changed'] is False
        assert len(audit(db)) == 1

    def test_unknown_id_is_404(self, client, db):
        login(client, db)
        assert client.post('/errors/999/resolve').status_code == 404
        assert audit(db) == []

    def test_operator_403_and_unauthenticated_401(self, client, db):
        a = db.log_error('E', 'm', 's')
        assert client.post(f'/errors/{a}/resolve').status_code == 401
        login(client, db, 'operator')
        assert client.post(f'/errors/{a}/resolve').status_code == 403
        assert not resolved(db, a) and audit(db) == []

    def test_buttons_only_for_admin_on_both_pages(self, client, db):
        db.log_error('E', 'm', 's')
        login(client, db, 'operator')
        assert 'data-resolve' not in client.get('/kiosk').text
        assert 'data-resolve' not in client.get('/logs').text
        login(client, db, 'admin', 'ann')
        assert 'data-resolve' in client.get('/kiosk').text
        assert 'data-resolve' in client.get('/logs').text


class TestTouchscreen:
    def test_data_viewer_marks_the_selected_unresolved_row(self, qapp, db, client):
        a = db.log_error('Printing Error', 'jam', 's')
        viewer = DataViewerController(MagicMock(), db)
        viewer.on_enter()
        view = viewer.view
        assert not view.resolve_button.isEnabled()
        view.error_log_table.selectRow(0)
        assert view.resolve_button.isEnabled()

        view.resolve_button.click()

        assert resolved(db, a)
        assert audit(db) == [('kiosk', 'touchscreen', 'error_resolved', f'#{a} Printing Error: jam', 'resolved')]
        assert view.error_log_table.item(0, 4).text() == 'yes'
        view.error_log_table.selectRow(0)
        assert not view.resolve_button.isEnabled()  # already resolved

    def test_both_sides_share_the_row_and_the_count(self, qapp, db, client):
        a = db.log_error('E', 'one', 's')
        b = db.log_error('E', 'two', 's')
        viewer = DataViewerController(MagicMock(), db)
        viewer.on_enter()
        viewer.view.error_log_table.selectRow(1)  # newest first, so row 1 is the older error
        viewer.view.resolve_button.click()
        login(client, db)
        assert client.get('/kiosk/data').json()['error_total'] == db.count_unresolved_errors() == 1
        assert {resolved(db, a), resolved(db, b)} == {True, False}


class TestPinOverride:
    def test_override_resolves_the_error_the_screen_logged(self, qapp, db, db_path, monkeypatch):
        import database.db_manager
        import utils.error_logger
        from screens.thank_you.model import ThankYouModel
        monkeypatch.setattr(utils.error_logger, 'log_error', lambda t, m, c: db.log_error(t, m, c))
        monkeypatch.setattr(database.db_manager, 'DatabaseManager', lambda: DatabaseManager(db_path=db_path))
        other = db.log_error('QR Reader', 'unrelated', 'qr')

        model = ThankYouModel()
        model.main_app = MagicMock()
        model.show_printing_error('Printer is paused (CUPS queue disabled)')
        mine = model.error_id
        assert mine is not None and db.count_unresolved_errors() == 2

        model.handle_admin_override()

        assert resolved(db, mine) and not resolved(db, other)
        assert audit(db)[0][:3] == ('kiosk', 'touchscreen', 'error_resolved')
        model.main_app.show_screen.assert_called_with('admin')

    def test_override_without_a_logged_error_resolves_nothing(self, qapp, db, monkeypatch):
        from screens.thank_you.model import ThankYouModel
        db.log_error('QR Reader', 'unrelated', 'qr')
        model = ThankYouModel()
        model.main_app = MagicMock()
        model.show_no_paper_error(0)

        model.handle_admin_override()

        assert db.count_unresolved_errors() == 1 and audit(db) == []


class TestKioskAdminCount:
    def test_admin_screen_shows_the_dashboards_count(self, qapp, db, client):
        from screens.admin.view import AdminScreenView
        db.log_error('E', 'a', 's')
        db.log_error('E', 'b', 's')
        login(client, db)
        view = AdminScreenView()
        view.update_unresolved_errors(db.count_unresolved_errors())
        assert view.unresolved_errors_label.text() == f"{client.get('/kiosk/data').json()['error_total']} unresolved"
        view.update_unresolved_errors(0)
        assert view.unresolved_errors_label.text() == 'None unresolved'
