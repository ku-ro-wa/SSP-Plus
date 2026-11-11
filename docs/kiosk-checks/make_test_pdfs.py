"""Make the test PDFs for the 2026-11-12 kiosk checks.

The small ones are committed next to this script. The two large ones (for the upload
timing check) aren't, so they don't sit in git history; make them on the kiosk:

    cd ~/SSP-Plus && .venv/bin/python docs/kiosk-checks/make_test_pdfs.py --big

Each page says which file it's from and its page number in large print, like the
A-D files from 2026-11-11.
"""
import argparse
import os
import random

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
COLOURS = [(0.85, 0.1, 0.1), (0.1, 0.55, 0.2), (0.1, 0.3, 0.85), (0.95, 0.75, 0.1),
           (0.6, 0.1, 0.7), (0.05, 0.65, 0.75)]


def labelled_page(doc, label, page_no, colour=None):
    page = doc.new_page(width=595, height=842)  # A4 in points
    if colour:
        page.draw_rect(fitz.Rect(40, 40, 555, 802), color=colour, fill=colour, fill_opacity=0.35)
    page.insert_text((70, 380), f"{label}", fontsize=96)
    page.insert_text((70, 520), f"page {page_no}", fontsize=72)
    return page


def labelled_pdf(path, label, pages, colour):
    doc = fitz.open()
    for n in range(1, pages + 1):
        labelled_page(doc, label, n, COLOURS[(n - 1) % len(COLOURS)] if colour else None)
    doc.save(path)
    doc.close()


def password_pdf(path):
    doc = fitz.open()
    labelled_page(doc, "E", 1)
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner-1234", user_pw="1234")
    doc.close()


def padded_pdf(path, label, megabytes):
    """One labelled page carrying a noise image, so the file is about `megabytes` MB
    (noise doesn't compress)."""
    side = int((megabytes * 1024 * 1024 / 3) ** 0.5)
    rng = random.Random(label)
    pix = fitz.Pixmap(fitz.csRGB, side, side, bytes(rng.getrandbits(8) for _ in range(side * side * 3)), False)
    doc = fitz.open()
    page = labelled_page(doc, label, 1)
    page.insert_image(fitz.Rect(70, 560, 525, 800), stream=pix.tobytes("png"))
    doc.save(path, deflate=False)
    doc.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--big", action="store_true",
                        help="make only the two large upload-timing files, in the home folder")
    args = parser.parse_args()

    if args.big:
        home = os.path.expanduser("~")
        for label, mb in (("H-about-1MB", 1), ("I-about-24MB", 24)):
            path = os.path.join(home, f"{label}.pdf")
            padded_pdf(path, label[0], mb)
            print(f"{path}: {os.path.getsize(path) / 1024 / 1024:.1f} MB")
        return

    password_pdf(os.path.join(HERE, "E-password-protected.pdf"))
    labelled_pdf(os.path.join(HERE, "F-color-10-pages.pdf"), "F", 10, colour=True)
    labelled_pdf(os.path.join(HERE, "G-color-50-pages.pdf"), "G", 50, colour=True)
    batch = os.path.join(HERE, "batch-of-21")
    os.makedirs(batch, exist_ok=True)
    for n in range(1, 22):
        labelled_pdf(os.path.join(batch, f"batch-{n:02d}.pdf"), f"batch {n:02d}", 1, colour=False)
    print("done")


if __name__ == "__main__":
    main()
