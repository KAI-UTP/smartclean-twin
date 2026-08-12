"""Convert the SmartClean Twin notebooks to PDF without LaTeX or pandoc.

Each notebook is exported to HTML with nbconvert, print CSS is injected so that
wide tables and long output lines wrap instead of being clipped at the page
edge, and headless Chrome prints the page to PDF.

Run it with MAKE-PDFS.bat, or directly:
    py scripts\\notebooks_to_pdf.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

REPO = r"D:\UTP\UG Y2S3\03 Digital Twin\smartclean-twin"
OUT_DIR = r"D:\UTP\UG Y2S3\03 Digital Twin\submission-pdfs"

NOTEBOOKS = [
    "submission_1_visualization",
    "submission_2_ai_model",
    "submission_3_data_streaming",
    "submission_4_dev_practices",
    "submission_5_deployment",
    "project_walkthrough",
]

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

PRINT_CSS = """
<style>
@page { size: A4 portrait; margin: 11mm; }
body { font-size: 10pt; }
.jp-RenderedHTMLCommon table, table {
  width: 100% !important; table-layout: auto !important;
  font-size: 8.5pt !important; border-collapse: collapse;
}
.jp-RenderedHTMLCommon th, .jp-RenderedHTMLCommon td, th, td {
  white-space: normal !important; overflow-wrap: break-word !important;
  padding: 3px 5px !important; max-width: none !important;
}
pre, code, .jp-OutputArea-output pre {
  white-space: pre-wrap !important; overflow-wrap: break-word !important;
  font-size: 7.5pt !important;
}
.jp-Cell, .jp-OutputArea-output { overflow: visible !important; }
</style>
</head>"""


def find_browser() -> str | None:
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def main() -> int:
    browser = find_browser()
    if browser is None:
        print("ERROR: Chrome or Edge not found. Install either one and re-run.")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="nb2pdf_")
    ok = 0

    for name in NOTEBOOKS:
        ipynb = os.path.join(REPO, name + ".ipynb")
        if not os.path.exists(ipynb):
            print(f"SKIP  {name}: notebook not found")
            continue

        print(f"...   {name}: exporting to HTML")
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "html",
                "--output-dir",
                tmp,
                ipynb,
            ],
            capture_output=True,
            text=True,
        )
        html = os.path.join(tmp, name + ".html")
        if not os.path.exists(html):
            print(f"FAIL  {name}: HTML export failed\n{r.stderr[-400:]}")
            continue

        with open(html, encoding="utf-8") as f:
            content = f.read()
        if "@page { size: A4 portrait" not in content:
            content = content.replace("</head>", PRINT_CSS, 1)
            with open(html, "w", encoding="utf-8") as f:
                f.write(content)

        pdf_tmp = os.path.join(tmp, name + ".pdf")
        subprocess.run(
            [
                browser,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_tmp}",
                "file:" + urllib.request.pathname2url(html),
            ],
            capture_output=True,
            timeout=300,
        )
        if not os.path.exists(pdf_tmp):
            print(f"FAIL  {name}: Chrome did not produce a PDF")
            continue

        shutil.copy(pdf_tmp, os.path.join(OUT_DIR, name + ".pdf"))
        print(f"OK    {name}.pdf  ({os.path.getsize(pdf_tmp) // 1024} KB)")
        ok += 1

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{ok} of {len(NOTEBOOKS)} notebooks converted.")
    print("Output folder:", OUT_DIR)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
