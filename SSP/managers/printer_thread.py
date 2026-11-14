import os
import subprocess
import tempfile
import time
from PyQt5.QtCore import QThread, pyqtSignal
from managers.printer_ipp import MEDIA_EMPTY_REASONS, has_reason, ipp_reasons
from managers.sms_manager import send_paper_jam_sms, send_printing_error_sms, send_no_paper_sms

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


def parse_printer_alerts(lpstat_output):
    """Return the alert words from `lpstat -l -p <printer>` output (empty when there are none)."""
    for line in lpstat_output.split('\n'):
        line = line.strip()
        if line.startswith("Alerts:"):
            alerts_text = line.replace("Alerts:", "").strip()
            if not alerts_text or alerts_text == "none":
                return []
            return alerts_text.split()
    return []


def remove_temp_pdf(path):
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            print(f"Error cleaning up temp file: {e}")


class PrinterThread(QThread):
    """Prints a transaction's items (managers/print_items.py): one CUPS job per
    item, last item first, each item's pages last first (#118), so the tray
    stack reads item 1 page 1 on top. Positions are 1-based print order.

    Every temporary PDF is built before the first job is submitted: the source
    files live in a Session folder that another customer's timeout can delete."""
    file_started = pyqtSignal(int, int)    # position, total: before each submission
    file_printed = pyqtSignal(int, str)    # position, temp PDF path (kept for ink analysis)
    print_success = pyqtSignal()           # after the last item
    print_failed = pyqtSignal(str)
    print_waiting = pyqtSignal()
    paper_empty = pyqtSignal()  # the printer itself says the tray is empty (sent just before print_failed)

    def __init__(self, items, printer_name):
        super().__init__()
        self.items = list(items)
        self.printer_name = printer_name
        self.temp_pdfs = {}     # position -> temp PDF path, until printed or cleaned up

    def run(self):
        sim_mode = os.getenv('SIM_MODE', 'false').lower() in ('true', '1', 'yes')
        total = len(self.items)

        if not PYMUPDF_AVAILABLE:
            if sim_mode:
                print("[SIM] PyMuPDF unavailable — simulating print job without temp PDFs.")
                for position in range(total, 0, -1):
                    self.file_started.emit(position, total)
                    self.file_printed.emit(position, "")
                self.print_success.emit()
                return
            self.print_failed.emit("PyMuPDF library is not installed.")
            return

        try:
            for position, item in enumerate(self.items, start=1):
                self.temp_pdfs[position] = self.create_temp_pdf(item)
        except Exception as e:
            print(f"Failed to create temporary PDF: {e}")
            self._cleanup_pending()
            self.print_failed.emit(f"Failed to create temporary PDF: {e}")
            return

        try:
            for position in range(total, 0, -1):
                item = self.items[position - 1]
                temp_path = self.temp_pdfs[position]
                if not self._print_item(position, total, item, temp_path, sim_mode):
                    return
                del self.temp_pdfs[position]   # printed: the receiver owns it now
                self.file_printed.emit(position, temp_path)
            self.print_success.emit()
        except Exception as e:
            self._handle_print_error(f"An unexpected error occurred: {str(e)}")
        finally:
            self._cleanup_pending()

    def _print_item(self, position, total, item, temp_path, sim_mode):
        """Submit one item's job and wait for it. True if it printed; on False
        print_failed has been emitted (or raised into run())."""
        command = self.build_print_command(item, temp_path)
        print(f"Printing file {position} of {total}: {len(item.pages)} pages x {item.copies} copies = {item.sheets} total pages")
        print(f"Command: {' '.join(command)}")
        print(f"Temp PDF: {temp_path}")

        if not os.path.exists(temp_path):
            raise FileNotFoundError(f"Temporary PDF not found: {temp_path}")

        self.file_started.emit(position, total)

        if sim_mode:
            print(f"[SIM] Skipping CUPS submission. Would run: {' '.join(command)}")
            time.sleep(1)
            return True

        # No timeout — large jobs can take a long time to spool
        process = subprocess.run(command, capture_output=True, text=True, check=True)

        if not process.stdout or "request id is" not in process.stdout:
            self.print_failed.emit("Print job was not accepted by CUPS. Check printer connection.")
            return False

        job_id = self._extract_job_id(process.stdout)
        if not job_id:
            return False

        self.print_waiting.emit()
        if not self.wait_for_print_completion(job_id):
            # The job was reported failed (and the customer refunded), so
            # it must not print later once the fault is cleared.
            self._cancel_cups_job(job_id)
            return False
        return True

    def _cleanup_pending(self):
        """Delete the temporary PDFs of items that were not printed."""
        for path in self.temp_pdfs.values():
            remove_temp_pdf(path)
        self.temp_pdfs.clear()

    def _cancel_cups_job(self, job_id):
        try:
            subprocess.run(['cancel', job_id], capture_output=True, text=True, timeout=10)
            print(f"Cancelled CUPS job {job_id}")
        except Exception as e:
            print(f"Could not cancel CUPS job {job_id}: {e}")

    def _extract_job_id(self, cups_output):
        try:
            parts = cups_output.split("request id is")
            if len(parts) > 1:
                job_id_part = parts[1].strip()
                job_id = job_id_part.split()[0].split('(')[0]
                print(f"Print job ID: {job_id}")
                return job_id
            else:
                self.print_failed.emit("Could not extract print job ID from CUPS response.")
                return None
        except Exception as e:
            print(f"Error extracting job ID: {e}")
            self.print_failed.emit(f"Error processing CUPS response: {e}")
            return None

    def _handle_print_error(self, error_message):
        print(f"ERROR: {error_message}")
        try:
            send_printing_error_sms(error_message)
        except Exception as sms_error:
            print(f"Failed to send SMS notification: {sms_error}")

        try:
            from utils.error_logger import log_error
            log_error("Printing Error", error_message, "printer_manager")
        except Exception as db_error:
            print(f"Failed to log error to database: {db_error}")

        self.print_failed.emit(error_message)

    def create_temp_pdf(self, item):
        """The item's selected pages, last page first, in a temporary PDF. Returns its path."""
        pages = sorted(item.pages)
        print(f"Creating temp PDF with pages: {pages}")

        if not item.path or not os.path.exists(item.path):
            raise FileNotFoundError(f"Source PDF file not found: {item.path}")

        original_doc = fitz.open(item.path)
        temp_path = None
        try:
            max_page = len(original_doc)
            invalid_pages = [p for p in pages if p < 1 or p > max_page]
            if invalid_pages:
                raise ValueError(f"Invalid page numbers: {invalid_pages}")

            # Last page first: the HP Smart Tank puts each sheet face up on top of the
            # last, so sending the pages in reading order leaves the stack reversed
            # (issue #118). The reversal lives here only.
            temp_doc = fitz.open()
            for page_num in (p - 1 for p in reversed(pages)):
                temp_doc.insert_pdf(original_doc, from_page=page_num, to_page=page_num)

            if len(temp_doc) != len(pages):
                raise ValueError(f"Page count mismatch! Expected {len(pages)}, got {len(temp_doc)}")

            fd, temp_path = tempfile.mkstemp(suffix=".pdf", prefix="printjob-")
            os.close(fd)
            temp_doc.save(temp_path, garbage=4, deflate=True)
            temp_doc.close()
            return temp_path
        except Exception:
            remove_temp_pdf(temp_path)
            raise
        finally:
            original_doc.close()

    def wait_for_print_completion(self, job_id):
        min_print_time = 15       # Enforce minimum to avoid false-positive completion at startup
        post_completion_wait = 5  # Buffer period after job disappears from queue
        check_interval = 3
        initial_startup_delay = 5

        # An empty tray is only a failure while the job is still unfinished. The sheet
        # that empties the tray is also the job's last one, so the printer raises
        # media-empty as the job finishes; a real paper-out mid-job leaves the job stuck
        # in the queue, and that is what this grace period waits out.
        tray_empty_grace = 30

        elapsed_time = 0
        completion_time = None
        media_empty_sms_sent = False
        tray_empty_since = None

        time.sleep(initial_startup_delay)
        elapsed_time += initial_startup_delay

        while True:
            try:
                target_printer = self.printer_name
                printer_actively_printing = False

                tray_empty = False
                alerts_result = subprocess.run(
                    ['lpstat', '-l', '-p', target_printer],
                    capture_output=True, text=True
                )

                if alerts_result.returncode == 0:
                    lpstat_out_lower = alerts_result.stdout.lower()
                    if " now printing " in lpstat_out_lower:
                        printer_actively_printing = True

                    alerts_found = self._without_stale_tray_alerts(
                        parse_printer_alerts(alerts_result.stdout), target_printer)
                    if alerts_found:
                        if "cups-waiting-for-job-completed" in alerts_found:
                            printer_actively_printing = True

                        if "media-jam-error" in alerts_found or "paper-jam" in alerts_found:
                            self.print_failed.emit(f"Paper jam detected on {target_printer}")
                            try:
                                send_paper_jam_sms()
                            except Exception:
                                pass
                            return False
                        elif any(a in alerts_found for a in ("media-empty-error", "media-needed-error",
                                                             "media-empty-report")):
                            tray_empty = True
                        elif "paused" in alerts_found:
                            # CUPS sets this when it disables the queue (e.g. after a backend
                            # failure); the job stays queued, so it would never count as complete
                            self.print_failed.emit(f"Printer {target_printer} is paused (CUPS queue disabled)")
                            return False
                        elif "offline" in alerts_found or "stopped" in alerts_found:
                            self.print_failed.emit(f"Printer {target_printer} is offline")
                            return False
                        elif "error" in alerts_found:
                            self.print_failed.emit(f"Printer error on {target_printer}")
                            return False

                cups_job_still_active = self._check_cups_job_status(job_id)

                if tray_empty:
                    if tray_empty_since is None:
                        tray_empty_since = elapsed_time
                        if not media_empty_sms_sent:
                            media_empty_sms_sent = True
                            try:
                                send_no_paper_sms()
                            except Exception:
                                pass
                    job_over = not printer_actively_printing and not cups_job_still_active
                    if job_over and elapsed_time >= min_print_time:
                        # Everything printed and the tray is now empty: the job succeeded,
                        # but the paper count is wrong and must be zeroed.
                        self.paper_empty.emit()
                        return True
                    if not job_over and elapsed_time - tray_empty_since >= tray_empty_grace:
                        self.paper_empty.emit()
                        self.print_failed.emit(f"No paper detected on {target_printer}")
                        return False
                    time.sleep(check_interval)
                    elapsed_time += check_interval
                    continue
                tray_empty_since = None

                if not printer_actively_printing and not cups_job_still_active:
                    if elapsed_time < min_print_time:
                        time.sleep(check_interval)
                        elapsed_time += check_interval
                        continue

                    if completion_time is None:
                        completion_time = elapsed_time
                    elif elapsed_time - completion_time >= post_completion_wait:
                        return True
                else:
                    completion_time = None

                time.sleep(check_interval)
                elapsed_time += check_interval

            except Exception as e:
                print(f"Error checking print status: {e}")
                time.sleep(check_interval)
                elapsed_time += check_interval

    @staticmethod
    def _without_stale_tray_alerts(alerts, printer_name):
        """CUPS can keep a media-empty alert after paper was loaded again, which
        would zero the paper count when the job ends. When it lists one, ask the
        printer; if it answers and reports no empty tray, drop CUPS' alert. A
        printer that can't be asked leaves the alerts as they were."""
        if not has_reason(alerts, MEDIA_EMPTY_REASONS):
            return alerts
        try:
            reasons = ipp_reasons(printer_name)
        except Exception:
            return alerts
        if reasons is None or has_reason(reasons, MEDIA_EMPTY_REASONS):
            return alerts
        return [a for a in alerts if not has_reason([a], MEDIA_EMPTY_REASONS)]

    def _check_cups_job_status(self, job_id):
        try:
            result = subprocess.run(['lpstat', '-o'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if job_id in line:
                        return True
            return False
        except Exception:
            return True

    def build_print_command(self, item, temp_path):
        mode_str = "color" if item.color_mode == "Color" else "monochrome"
        return [
            "lp",
            "-d", self.printer_name,
            "-o", f"print-color-mode={mode_str}",
            "-o", "job-sheets=none",
            # Whole sets (1,2,3,1,2,3) rather than the printer's default per-page order
            "-o", "collate=true",
            "-n", str(item.copies),
            temp_path,
        ]
