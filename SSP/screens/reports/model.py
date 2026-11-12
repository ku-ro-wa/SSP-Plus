# screens/reports/model.py

from managers.accounting_report import accounting_data, collection_figures

# Button label and range key, in the order the dashboard offers them.
RANGES = (("Today", "today"), ("This week", "week"), ("This month", "month"), ("All time", "all"))

# How many past collections the screen lists (the dashboard lists them all).
COLLECTIONS_SHOWN = 4


class ReportsModel:
    """The figures /accounting shows, read through the same code
    (managers/accounting_report.py) so the two can't disagree (issue #130)."""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.range_key = "today"

    def report(self, range_key=None):
        """{'range', 'sources', 'vouchers', 'cash'} for `range_key` (default: the current one).
        `sources` and `vouchers` are exactly /accounting/data's; `cash` is /accounting/collections'."""
        if range_key is not None:
            self.range_key = range_key
        data = accounting_data(self.db_manager, self.range_key)
        data["cash"] = collection_figures(self.db_manager)
        return data
