# Kiosk checks, 2026-11-11

A walkthrough for checking everything that changed after the evening of 2026-11-10 on the
real kiosk (the newer unit). It assumes you know nothing about those changes. Follow it top
to bottom. Every command is meant to be copied exactly as written.

**What this is for.** The kiosk still runs the code from about 9–10 pm on Nov 10 (the fix that
stops two copies of the app running at once). Since then, seven pull requests were merged
into `main` without ever running on the kiosk, and four more are waiting for a kiosk test
before they can be merged. This walkthrough:

1. updates the kiosk to `main`, after backing up its database;
2. checks the seven merged changes (Part 4);
3. optionally checks the four open PRs: print order and printing several files in one
   transaction (Part 5);
4. puts the kiosk back the way it was (Part 6).

**Time:** about 1.5 hours for Parts 1–4 and 6, plus about an hour for Part 5.

**If something goes wrong:** don't try to fix the code. Write down what you saw: take a
photo of the screen and copy the last 50 lines of the log (Part 2, step 4). Then put the
kiosk back on `main` (Part 6) and tell Riley. A failed check is a useful result.

**Words used below:**
- **Kiosk Admin**: the admin screen on the touchscreen. Tap **Admin** (on the idle or
  homepage screen), then enter the admin PIN.
- **Admin Dashboard**: a separate website for reports, opened in the laptop's browser.
- **Session**: a batch of uploaded files plus its 6-digit pickup code.
- **Voucher**: credit the kiosk issues instead of cash (as a code and a QR).

---

## Part 0. What to bring

- **A laptop.** Windows works; the steps below are written for Windows. It needs Wi-Fi
  internet: the kiosk downloads the update through it, and email only works through it.
- **An Ethernet cable**, from the laptop to the kiosk. If the laptop has no Ethernet port,
  bring a USB-Ethernet adapter.
- **A phone** that can join the kiosk's own Wi-Fi network (`AIO-SPARK`).
- **A USB flash drive** with the test PDFs from this folder on it:
  `A-color-1-page.pdf`, `B-bw-3-pages.pdf`, `C-bw-5-pages.pdf`, `D-color-20-pages.pdf`. Each
  page says which file it's from and its page number in large print, so you can check the
  order of the printed stack. Download them from GitHub: open each file, then **Download raw
  file**. Put the same four files on the phone as well.
- **The kiosk login and the admin PIN**, from the team's credential store. The kiosk's
  user name is `group-c` and its network name is `aio-spark-kiosk`.
- **Paper:** about 20 sheets for Part 4, plus about 80 more for Part 5.
- **Cash** for test payments: ₱1, ₱5 and ₱10 coins, and ₱20/₱50/₱100 bills. Part 4 costs
  very little. Part 5 costs about ₱300 in all (a 20-page color file is ₱100), but it all goes
  into the cash box, so you get it back.

---

## Part 1. Connect the laptop to the kiosk

You need a terminal on the kiosk (an "SSH session") to update it. The kiosk's own Wi-Fi
blocks SSH on purpose, so use the Ethernet cable.

1. Connect the laptop to the internet over Wi-Fi as usual.
2. Plug the Ethernet cable into the laptop and into the kiosk's Pi.
3. **Share the laptop's internet with the kiosk:**
   1. Press **Win+R**, type `ncpa.cpl`, press Enter. The *Network Connections* window opens.
   2. Right-click your **Wi-Fi** adapter (not Ethernet), then **Properties**, then the
      **Sharing** tab.
   3. Tick **Allow other network users to connect through this computer's Internet
      connection**.
   4. Under *Home networking connection*, pick the **Ethernet** adapter the cable is in.
      Click **OK**.
   5. Unplug the Ethernet cable from the kiosk, wait 5 seconds, then plug it back in. Wait
      30 seconds while the kiosk gets an address.
4. **Open PowerShell** (Start menu, type `powershell`, press Enter) and check you can reach
   the kiosk:

   ```powershell
   ping aio-spark-kiosk.local
   ```

   Replies mean it works. If you see "could not find host", find the kiosk's address
   instead:

   ```powershell
   arp -a
   ```

   Look under `Interface: 192.168.137.1` for a `dynamic` line, for example `192.168.137.45`.
   That number is the kiosk's address. Use it **everywhere this guide says
   `aio-spark-kiosk.local`**.
5. **Log in to the kiosk:**

   ```powershell
   ssh group-c@aio-spark-kiosk.local
   ```

   The first time, it asks "Are you sure you want to continue connecting?". Type `yes`. Then
   enter the kiosk's password; nothing shows while you type. Once you're in, the prompt
   changes to `group-c@aio-spark-kiosk:~ $`. **Every command from here on is typed into this
   window**, unless it says PowerShell on the laptop.
6. **Check the kiosk has internet:**

   ```bash
   ping -c 3 github.com
   ```

   You should see 3 replies. If not, go back to step 3: turn sharing off, then on again,
   and replug the cable. Without internet the update can't download and email can't work.
   Everything else in Part 4 still can, so carry on without them if you have to.

If the SSH window closes or freezes at any point, open a new PowerShell and run step 5
again. The kiosk app keeps running on its own whether or not you're connected.

---

## Part 2. Back up the kiosk and note how it looks now

The app runs by itself as a background service called `ssp-kiosk`: it starts at boot and
restarts within about 5 seconds if it crashes. To stop it, you must use the command below.
Closing the window on the touchscreen just makes it come back.

1. **Stop the app** (the touchscreen goes to the desktop):

   ```bash
   systemctl --user stop ssp-kiosk
   ```

2. **Back up the database** into one file, then check the copy:

   ```bash
   cd ~/SSP-Plus
   .venv/bin/python -c "import sqlite3; s=sqlite3.connect('SSP/database/ssp_database.db'); d=sqlite3.connect('/home/group-c/ssp_database-before-update-2026-11-11.db'); s.backup(d); d.close(); print('backup ok')"
   ls -l ~/ssp_database-before-update-2026-11-11.db
   ```

   It should print `backup ok` and a file of a few hundred KB.
   **Copy it to the laptop as well.** In a *second* PowerShell window on the laptop (not the
   SSH one):

   ```powershell
   scp group-c@aio-spark-kiosk.local:ssp_database-before-update-2026-11-11.db $HOME\Desktop\
   ```

   It's now on the laptop's desktop. Keep it, and don't send it around: it holds every
   transaction.
3. **Note where the kiosk is now**, and check nobody changed code on it:

   ```bash
   git log --oneline -1
   git status --short
   ```

   Write down the first line, the commit. `git status --short` should print **nothing**.
   If it prints file names, someone edited files on the kiosk. **Stop here** and send Riley
   the output: updating would mix their changes in.
4. **How to read the app's log** (you'll need this in later steps). In a separate SSH
   window, run:

   ```bash
   tail -f ~/SSP-Plus/SSP/logs/app.log
   ```

   It shows everything the app prints, with times, as it happens. Press **Ctrl+C** to stop
   watching; that doesn't stop the app. To get the last 50 lines for a report, run
   `tail -n 50 ~/SSP-Plus/SSP/logs/app.log`.
5. **Keep the logs across reboots**, so a crash today is still in the logs tomorrow. It's
   a one-time fix:

   ```bash
   sudo mkdir -p /var/log/journal && sudo systemctl restart systemd-journald
   ```

---

## Part 3. Update the kiosk to `main`

1. Download the update and switch to it:

   ```bash
   cd ~/SSP-Plus
   git fetch origin
   git checkout main
   git pull --ff-only origin main
   git log --oneline -1
   ```

   The last line should start with `88a605b` (`Merge pull request #117`). If `git pull`
   fails, send Riley the output and put the old version back with
   `git checkout <the commit you wrote down>`.
   No new Python packages are needed for this update.
2. **Start the app again:**

   ```bash
   systemctl --user start ssp-kiosk
   sleep 15
   systemctl --user status ssp-kiosk --no-pager | head -5
   tail -n 30 ~/SSP-Plus/SSP/logs/app.log
   ```

   `status` should say `active (running)`, and the idle screen should be on the
   touchscreen. The first start creates the new database tables by itself. If the screen
   stays on the desktop for more than a minute, send Riley the `tail` output.

---

## Part 4. Check the merged changes

Write the result of each check in the results table at the end (Part 7). The PR number in
each heading is the change being checked.

### 4.1 Kiosk Admin fits the screen, with Collect cash and Settings (#116, #117)

1. Tap **Admin** and enter the PIN.
2. Check the whole screen is visible on the panel, with nothing cut off at the bottom or
   the right:
   - the **Coin Inventory** row ends with **Refill All** and a new **Collect cash** button;
   - the bottom row has **Back to Main Screen**, **View Data Logs** and a new **Settings**
     button.
3. Take a photo of the whole screen.
4. **Write down** the paper count and the ₱1 and ₱5 coin counts shown. You'll need them in
   4.6.

### 4.2 The Settings screen (#117)

1. In Kiosk Admin, tap **Settings**. It lists 7 settings: Voucher expiry, Voucher lockout,
   Pickup window, Maximum change, Keep ₱1 coins in reserve, Keep ₱5 coins in reserve, and
   Low-change warning.
2. Check the whole screen fits the panel, and take a photo.
3. **Changes apply without restarting the app:**
   1. Tap the **Low-change warning** field. Type `1000` on the on-screen keypad and tap
      **Save**. Check that every key you tapped registered: this keypad has small keys and
      has never been used on the real panel.
   2. Go back to the idle screen. A low-change warning banner should now show. Since the
      kiosk never holds ₱1000 of change, it always warns at 1000.
   3. Go back to Settings, set **Low-change warning** to `20`, and tap **Save**. On the idle
      screen, the banner should be gone, unless the hoppers really are low on coins.
4. Try a value out of range, for example `99999` for Pickup window, and tap Save. It
   should refuse with a message and save nothing.

### 4.3 Pickup codes: reusable, and expired files deleted (#111)

A pickup code now works as many times as you like for 12 hours. After that, the kiosk
deletes the files on its own within about 5 minutes. To see the deletion without waiting 12
hours, shorten the window for one upload.

1. In Kiosk Admin → **Settings**, set **Pickup window** to `1` (minute) and tap **Save**.
2. On the phone, join the Wi-Fi network **AIO-SPARK**. On the kiosk, go to the homepage and
   tap **WiFi**. The screen shows a web address. Open it in the phone's browser and upload
   `A-color-1-page.pdf`. The phone shows a 6-digit code: write it down.
3. **Right away**, at the kiosk's **WiFi** screen, type the code and tap **Send**. The file
   list opens with the file. Tap **Back** until you're at the homepage. Then type the code
   a **second time**: it should open again.
4. Set **Pickup window** back to `720` and tap **Save**. This only changes new uploads, so
   the one from step 2 still expires after 1 minute.
5. Go to 4.4 now. Come back here in 6 minutes or more.
6. After the 6 minutes, check the log:

   ```bash
   grep "expired session" ~/SSP-Plus/SSP/logs/app.log | tail -3
   ```

   It should print a recent line like `Removed 1 expired session(s)`. Then check the files
   were deleted. This lists the upload folder, which should no longer contain that upload:

   ```bash
   ls -lt ~/SSP-Plus/SSP/database/wifi_uploads | head
   ```

7. Type the code on the WiFi screen again. It should say **Incorrect or expired code**.

### 4.4 Limit on wrong pickup codes, at the kiosk (#113)

Five wrong typed codes in a row lock code entry on **both** the WiFi and Email screens for 5
minutes.

1. On the homepage tap **WiFi**. Type `000000` and **Send**, five times. After the fifth:
   - the keypad, the entry field and **Send** turn grey (disabled);
   - a banner says **Too many wrong codes. Try again in 4:59.** and counts down.
2. Tap Back, then **Email**. It should be locked too, with the same countdown.
3. Restart the app while it's locked, then check it's still locked:

   ```bash
   systemctl --user restart ssp-kiosk
   ```

   Go back to the WiFi screen: it should still be counting down.
4. Wait for the countdown to finish, about 5 minutes. Entry works again.
5. A **real** code typed on the wrong screen does **not** count as a wrong guess. A
   customer holding an Email code could easily tap the WiFi tile by mistake. To check: if
   you get a code by email in 4.6, type it on the **WiFi** screen five times. It should
   never lock.

### 4.5 Limit on wrong pickup codes, on the phone (#113)

The phone page also has a code box, `/redeem`, for picking up scanned digital copies. Five
wrong codes from one phone within 15 minutes block that phone for a while.

1. On the phone, still on **AIO-SPARK**, open the same web address as in 4.3 with
   `/redeem` added at the end (for example `https://<address>/redeem`).
2. Enter `000000` and submit, six times. The first five say the code is wrong. The
   **sixth** should say **Too many incorrect codes. Try again in N minute(s).** Take a
   screenshot.
3. The kiosk's touchscreen is not affected: its WiFi screen still accepts codes.

Then go back to 4.3, step 6.

### 4.6 Email: several PDFs in one email (#114). Needs the kiosk online

1. On the homepage tap **Email**. The screen shows the kiosk's email address and the word
   that must be in the subject. Write both down.
2. From any email account, send **one** email to that address, with that word in the
   subject, and attach **two** PDFs: `B-bw-3-pages.pdf` and `C-bw-5-pages.pdf`. Note the
   time you send it.
3. A reply arrives with one code and one QR. Note how many seconds it took. Type the code
   on the **Email** screen: the file list should show **both** files.
4. Send a second email the same way, with `B-bw-3-pages.pdf` **and**
   `X-not-really-a-pdf.pdf` attached. **No** reply should come: the whole email is rejected
   and nothing is saved. Wait 2 minutes to be sure.

If the kiosk has no internet, skip 4.6 and write "not tested, no internet".

### 4.7 Admin Dashboard: its secret key, and the new pages (#115, #107, #117, #116)

The Admin Dashboard is a reports website that runs on the kiosk and opens in the laptop's
browser. It now refuses to start until the kiosk has its own secret key. The kiosk app
itself isn't affected by any of this.

1. **Check it refuses to start without a key:**

   ```bash
   cd ~/SSP-Plus
   grep -c '^ADMIN_DASHBOARD_SECRET_KEY=' .env; grep -c 'dev-insecure' .env
   make run-admin-dashboard
   ```

   If the second number is `1`, or the first is `0`, the key isn't set yet. The dashboard
   should then stop at once with `Admin Dashboard not started: ADMIN_DASHBOARD_SECRET_KEY
   is unset or still the development default`. Write that down: it's the check passing.
   If it starts instead, press Ctrl+C. The key is already set, so skip to step 3.
2. **Give the kiosk its own key.** Copy all three lines at once:

   ```bash
   KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   sed -i '/^ADMIN_DASHBOARD_SECRET_KEY=/d' .env && echo "ADMIN_DASHBOARD_SECRET_KEY=$KEY" >> .env
   grep -q '^ADMIN_DASHBOARD_SECRET_KEY=.\+' .env && ! grep -q 'dev-insecure' .env && echo ok
   ```

   It should print `ok`. Save the key in the team's credential store under "newer kiosk,
   dashboard key". To see it, run `grep '^ADMIN_DASHBOARD_SECRET_KEY' .env`. Never put it
   in chat, a screenshot or git.
3. **Make yourself a dashboard account.** Pick your own name and a password:

   ```bash
   PYTHONPATH=SSP .venv/bin/python -m admin_dashboard.cli create-account --username <yourname> --password '<a password>' --role admin
   ```

   If your name already exists, use `reset-password --username <yourname> --password '<a
   password>'` instead of `create-account ... --role admin`.
4. **Start the dashboard:**

   ```bash
   make run-admin-dashboard
   ```

   It should print that Uvicorn is running on port 8100. **Leave this SSH window open**.
   The dashboard runs only while it's open. Use another SSH window for everything else.
5. On the laptop's browser, open **http://aio-spark-kiosk.local:8100** (or
   `http://<kiosk address>:8100`) and log in.
6. **`/kiosk` page** (where you land after logging in). Check it against Kiosk Admin on
   the touchscreen:
   - the kiosk is shown **online**, last seen under about a minute ago;
   - the QR reader shows **Connected**;
   - the paper count, the ₱1/₱5 coin counts and the four ink levels match Kiosk Admin;
   - the error list shows recent errors, probably the pickup-code lockouts from 4.4 and 4.5.

   Take a screenshot.
7. **`/logs` page:** the transactions and errors are listed, 25 per page, and **Older** /
   **Newer** move between pages. Take a screenshot.
8. **`/settings` page:** it shows the same 7 settings as the touchscreen. Change
   **Low-change warning** to `25`, save, and check the touchscreen's Settings screen shows
   `25`. Then set it back to `20`.
9. **`/accounting` page:** take a screenshot with the range on **all**. The thesis needs
   it. Keep the dashboard running for 4.8.

### 4.8 Collect cash (#116)

"Collect cash" records how much money the kiosk holds, then sets every count to 0. It's
meant for when someone empties the cash box. Doing it now records a test collection. That's
fine; write "test collection" in the results.

1. In Kiosk Admin, tap **Collect cash**. A dialog lists every coin and bill with its
   count, and a total. Take a photo of it. Check it fits on the screen, with both buttons
   visible.
2. Tap **Cancel** first. Nothing should change. Then tap **Collect cash** again and
   confirm.
3. All counts now read **0**. Because the kiosk now believes it has no change, the idle
   screen shows the low-change warning. That's expected.
4. In the dashboard, refresh **/accounting**. A **Collected** table shows the collection
   with its breakdown and total. Take a screenshot.
5. **Put the hopper counts back**, or the kiosk will give no change to anyone. Use the ₱1
   and ₱5 numbers you wrote down in 4.1. Either tap **+** next to ₱1 Coins and ₱5 Coins
   until they match, or set both at once over SSH (put your two numbers in place of
   `36`):

   ```bash
   cd ~/SSP-Plus && .venv/bin/python -c "
   import sqlite3; c = sqlite3.connect('SSP/database/ssp_database.db')
   c.execute(\"UPDATE cash_inventory SET count=36 WHERE denomination=1 AND type='coin'\")
   c.execute(\"UPDATE cash_inventory SET count=36 WHERE denomination=5 AND type='coin'\")
   c.commit(); print(c.execute('SELECT denomination, type, count FROM cash_inventory').fetchall())"
   ```

   Leave Kiosk Admin and open it again. The ₱1 and ₱5 counts should show your numbers.
   The low-change banner on the idle screen should be gone.
6. Stop the dashboard: press **Ctrl+C** in its SSH window.

### 4.9 Restart test

1. Restart the kiosk:

   ```bash
   sudo reboot
   ```

   Your SSH session closes; that's expected.
2. Within about 2 minutes, the idle screen should come back on its own, with no one
   touching anything. Note how long it took.
3. Log in again (Part 1, step 5) and check it's on the new code and running:

   ```bash
   cd ~/SSP-Plus && git log --oneline -1 && systemctl --user status ssp-kiosk --no-pager | head -3
   ```

---

## Part 5 (optional). Test the open PRs: print order and several files

These four PRs need a real kiosk run before they can be merged:

- **#121** prints pages last first, so the stack in the output tray reads 1, 2, 3 from the
  top. The printer lays each sheet face up on the last one, so the order used to come out
  reversed. It also collates copies (1, 2, 3, 1, 2, 3).
- **#125–#127** let a customer tick several files and print them in one transaction, each
  file with its own color and copies setting.

They are stacked, so one branch, `feature/multi-file-ui`, contains all four. Load paper
first. After loading, set the paper count in Kiosk Admin with **Refill** so the count
matches the tray.

### 5.1 Switch the kiosk to the test branch

```bash
cd ~/SSP-Plus
systemctl --user stop ssp-kiosk
git fetch origin
git checkout feature/multi-file-ui
git pull --ff-only origin feature/multi-file-ui
git log --oneline -1
systemctl --user start ssp-kiosk
```

The last line should start with `a5f049a`. The app starts again on its own.

### 5.2 One file, as before (#121, #126)

Use the USB drive: on the homepage tap **USB**, then insert the drive.

1. **Page order and collated copies.** Pick `B-bw-3-pages.pdf`, all 3 pages, **2 copies**,
   B&W, and pay. Take the stack out of the tray **without turning it over**. Reading from
   the top, it should go: B page 1, 2, 3, then 1, 2, 3 again. Write down the order you
   got.
2. **Page subset.** Pick `C-bw-5-pages.pdf`, select only pages 2 and 4, 1 copy, and pay.
   From the top: page 2, then page 4.
3. **A long color job.** Pick `D-color-20-pages.pdf`, Color, 1 copy, and pay (₱100).
   - The thank-you screen should stay up the whole time the printer works, even past 2
     minutes, and must not jump back to idle mid-print.
   - Afterwards, the stack reads D page 1 to 20 from the top.
   - In Kiosk Admin, the paper count went down by 20 and the ink levels went down a little.
   - The temporary print files are gone:

     ```bash
     ls /tmp/printjob-*.pdf
     ```

     should say `No such file or directory`, a minute or so after the print ends.
4. **Paper runs out mid-job.** Start `B-bw-3-pages.pdf` with 2 copies again. As soon as
   the first sheet comes out, pull the remaining paper from the tray. The kiosk should end
   with a **refund Voucher for the whole job**. Take a photo of the Voucher screen. Put the
   paper back, then reset the paper count in Kiosk Admin.

### 5.3 Several files in one transaction (#127)

1. On the file screen, each file has a **tick box** beside it. Tapping the file name
   still only previews it. Tick, in this order:
   1. `A-color-1-page.pdf`
   2. `B-bw-3-pages.pdf`
   3. `C-bw-5-pages.pdf`, after selecting only pages 1–3 in its preview
   4. `D-color-20-pages.pdf`

   The ticks should show the numbers 1, 2, 3, 4 in the order you ticked. Untick B: the rest
   renumber to 1, 2, 3. Tick B again: it becomes 4. Then untick everything and tick them
   again in the order above.
2. Tap **Continue**. The print options screen shows **one row per file**. Set: A Color, 1
   copy. B B&W, **2 copies**. C B&W, 1 copy. D Color, 1 copy. Each row shows its own price,
   and **Continue** stays grey until every price has appeared. The rows should scroll by
   dragging.
3. **The "still calculating" bug.** Tap Continue to reach payment. Insert one ₱5 coin, then
   tap **Back**. Change B's copies to 1 and back to 2, then tap Continue again. You should
   reach payment with the ₱5 still credited, and **no** popup about the price still being
   calculated. Do Back and Continue a second time.
4. On the payment screen, the summary says **4 files**. Copies and color say **Varies**.
   Pay the rest.
5. The thank-you screen shows **Printing file 1 of 4**, then 2 of 4, and so on. The
   printer works through the files **last one first** (D, then C, B, A), so that the
   face-up stack ends up in order. The stack, from the top, should read: A1; B1, B2, B3,
   B1, B2, B3; C1, C2, C3; D1 to D20. Write down anything out of order.
6. **Paper runs out partway.** Tick A (Color, 1 copy), then B (B&W, **2 copies**), then C
   (pages 1–3 only, B&W, 1 copy), and pay (₱32). The printer does C first, then B, then A.
   As soon as C's 3 sheets are out and B's first sheet appears, pull the remaining paper.
   The kiosk should end with **one** Voucher, for B and A, which didn't print: ₱18 + ₱5
   = **₱23**. C, which did print, isn't refunded. Take a photo. Check the status:

   ```bash
   cd ~/SSP-Plus && .venv/bin/python -c "
   import sqlite3; c = sqlite3.connect('SSP/database/ssp_database.db')
   print(c.execute('SELECT id, timestamp, file_name, status, total_cost, voucher_issued FROM transactions ORDER BY id DESC LIMIT 3').fetchall())"
   ```

   The newest row should say `partly_printed`. Put the paper back and reset the paper count.
7. **Limit of 10 files.** Optional: needs 11 PDFs in one place. Ticking an 11th file is
   refused with a message.

Write the results of Part 5 as a comment on **PR #127**, and the page-order result (5.2.1)
on **PR #121** too.

---

## Part 6. Put everything back

1. **Back to `main`**, if you did Part 5:

   ```bash
   cd ~/SSP-Plus
   systemctl --user stop ssp-kiosk
   git checkout main
   git log --oneline -1
   systemctl --user start ssp-kiosk
   ```

   The commit should start with `88a605b`. The extra table that Part 5 added to the database
   is harmless on `main`.
2. In Kiosk Admin:
   - **paper count** = the sheets actually in the tray;
   - **₱1 and ₱5 coins** = what's in the hoppers;
   - **Settings**: Pickup window `720`, Low-change warning `20`.
3. Copy the database to the laptop again, for the record. Run this in the laptop's
   PowerShell:

   ```powershell
   ssh group-c@aio-spark-kiosk.local "cd ~/SSP-Plus && .venv/bin/python -c \"import sqlite3; s=sqlite3.connect('SSP/database/ssp_database.db'); d=sqlite3.connect('/home/group-c/ssp_database-after-checks-2026-11-11.db'); s.backup(d); d.close()\""
   scp group-c@aio-spark-kiosk.local:ssp_database-after-checks-2026-11-11.db $HOME\Desktop\
   ```

4. Also copy the app log:

   ```powershell
   scp group-c@aio-spark-kiosk.local:SSP-Plus/SSP/logs/app.log $HOME\Desktop\app-2026-11-11.log
   ```

5. On the laptop, turn internet sharing off again (Part 1, step 3, untick the box) if you
   don't need it.

---

## Part 7. Results

Copy this table into a comment on the pull request that added this guide, or into the
group chat, with the photos and screenshots. Mark each row **Pass**, **Fail** or **Not
done**, plus a note.

| # | Check | Result | Notes |
|---|---|---|---|
| 3 | Update to `main` (`88a605b`), app starts | | old commit: |
| 4.1 | Kiosk Admin fits; Collect cash and Settings buttons visible | | |
| 4.2 | Settings screen fits; keypad taps register; low-change warning applies without restart; out-of-range refused | | |
| 4.3 | Code works twice; expired upload deleted within ~6 min (`Removed 1 expired session(s)`); code then refused | | |
| 4.4 | 5 wrong codes lock WiFi **and** Email; countdown; still locked after restart; unlocks after 5 min | | |
| 4.4.5 | A real Email code typed on WiFi 5× doesn't lock | | |
| 4.5 | `/redeem`: 6th wrong code refused as "too many"; touchscreen unaffected | | |
| 4.6 | Email with 2 PDFs → 1 code, both files; email with the fake PDF → no reply | | seconds to reply: |
| 4.7 | Dashboard refused to start without a key; starts with one; key saved in credential store | | |
| 4.7 | `/kiosk` matches Kiosk Admin; online; QR Connected | | |
| 4.7 | `/logs` pages; `/settings` change shows on touchscreen; `/accounting` screenshot | | |
| 4.8 | Collect cash dialog fits; Cancel changes nothing; confirm zeroes counts; Collected table on `/accounting`; hopper counts restored | | |
| 4.9 | Reboot: app back on its own | | seconds: |
| 5.2.1 | 3 pages × 2 copies: stack 1,2,3,1,2,3 from top | | |
| 5.2.2 | Pages 2 and 4 only | | |
| 5.2.3 | 20-page color: thank-you stays up; paper and ink updated; `/tmp/printjob-*.pdf` gone | | |
| 5.2.4 | Paper pulled: full refund Voucher | | |
| 5.3.1–2 | Tick order numbers; one row per file; Continue waits for prices | | |
| 5.3.3 | Back from payment and return twice: no popup, ₱5 kept | | |
| 5.3.4–5 | "4 files" / "Varies"; "Printing file k of 4"; stack order | | |
| 5.3.6 | Paper pulled during file 2: one Voucher for the rest; `partly_printed` | | |
| 6 | Back on `main`; counts and settings restored; DB and log copied | | |

Also note anything odd you saw, even if no check covered it: a freeze, a restart, a coin
that didn't count, a screen that looked wrong.
