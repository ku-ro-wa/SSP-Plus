# Several files in one transaction

A Session can hold several files, but a transaction printed exactly one: to print three files the
customer paid and printed three times, or merged them into one PDF before uploading. Two
respondents in the field-deployment SUS survey asked for printing several files at once (#119).

## Decisions

- **One transaction, one payment, one price, many files.** The customer ticks files in
  `file_browser`; the order they tick them is the print order (shown as 1, 2, 3). Each file keeps its
  own pages, B&W/Color and copies (`managers/print_items.py`'s `PrintItem`). At most
  `MAX_FILES_PER_TRANSACTION` (10) files, so the `print_options` list stays short enough to scroll
  and a refund Voucher stays one number.

- **One CUPS job per file, sent last file first.** `print-color-mode` is set per job, so a
  transaction with a color file and a B&W file can't be one job. The tray stacks sheets face up, so
  sending the last file first (and each file's pages last first, #118) leaves file 1 page 1 on top.
  All temporary PDFs are built before the first job is submitted: file 1 would otherwise be read
  minutes after payment, by which time another customer's timeout may have deleted the Session
  folder (`cleanup_all_temp_folders()`).

- **The `transactions` row stays one row per payment.** `file_count` says how many files; for
  several files `pages` is the total sheets and `copies` is 1, so every existing query that
  multiplies them still gets the sheets printed. The per-file detail is in the new
  `transaction_files` table (position, name, pages, copies, mode, cost, status). Transactions
  from before it have no file rows and read as one file.

- **`partly_printed`.** If a file fails after others have printed, the transaction ends as
  `partly_printed`; if the first file fails it is the ordinary `print_failed` and a full refund.
  The files that didn't print (the failing one and every one after it) are refunded as **one
  Voucher** worth their summed cost, rounded once on the sum. **Revenue** for a `partly_printed`
  row is the cost of its `printed` files only, read from `transaction_files`; the transaction
  counts once. Change dispensed and Vouchers Applied include it, like `print_failed`. The
  Dashboard doesn't report it separately.

- **The thank-you screen never goes to idle while the print thread runs.** A 20-page color file
  takes longer than the 120 s safety redirect; the next customer would otherwise start while this
  job is still printing, and their timeout would delete its files.

## Not done

Reordering by dragging, combining files from different Sessions or Sources, and non-PDF files.
