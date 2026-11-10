# admin_dashboard/startup_check.py
#
# The login cookie is signed with ADMIN_DASHBOARD_SECRET_KEY. If that is unset
# or still the development default (which is public: it ships in .env.example),
# anyone can forge an admin cookie. With SIM_MODE off the dashboard must not
# start that way, the same way managers/gpio_check.py stops the kiosk without
# pigpio. In SIM_MODE the dev default stays so `make run-admin-dashboard` and
# the tests work unchanged.

DEV_SECRET_KEY = "dev-insecure-secret-change-me"


def secret_key_problem(config):
    """None if the dashboard may start; otherwise what's wrong and how to fix it."""
    if config.sim_mode:
        return None
    try:
        key = (config.get('ADMIN_DASHBOARD_SECRET_KEY', str) or "").strip()
    except KeyError:
        key = ""
    if key and key != DEV_SECRET_KEY:
        return None
    return (
        "ADMIN_DASHBOARD_SECRET_KEY is unset or still the development default, so "
        "dashboard logins could be forged. Set it in .env to a random value: "
        "python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
