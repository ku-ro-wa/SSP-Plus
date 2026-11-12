"""
What /logs on the Admin Dashboard and the touchscreen data viewer both show for
the transaction and error logs (issue #131): the page size and the column lists,
so the two can't drift apart. Rows come from DatabaseManager.get_transaction_page()
and get_error_page(), newest first.
"""

PAGE_SIZE = 25  # rows per page, on both sides

# Column headings, in order. The data viewer also puts an ID first, where it fits.
TRANSACTION_COLUMNS = ("Time", "File", "Source", "Pages", "Copies", "Colour", "Cost", "Paid", "Change", "Status")
ERROR_COLUMNS = ("Time", "Type", "Message", "Screen", "Resolved")

NUMERIC_COLUMNS = ("Pages", "Copies", "Cost", "Paid", "Change")


def page_count(total):
    """Pages needed for `total` rows; an empty log still has page 1."""
    return max(1, -(-total // PAGE_SIZE))
