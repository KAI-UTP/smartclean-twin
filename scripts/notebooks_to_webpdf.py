"""Convert the SmartClean Twin notebooks to PDF using nbconvert's WebPDF exporter.

Why this script exists instead of Jupyter's menu:
Jupyter's "Save and Export Notebook As -> PDF" converts through LaTeX, so it
needs pandoc plus a LaTeX engine (a multi-gigabyte install on Windows).
"Save and Export Notebook As -> WebPDF" avoids LaTeX, but it fails inside the
Jupyter server because the server forces the Windows *selector* asyncio event
loop, which cannot start the subprocess that Playwright needs. Running the same
exporter in a standalone process with the *proactor* policy works correctly.

Run with MAKE-PDFS.bat, or directly:
    py scripts\\notebooks_to_webpdf.py
"""

from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nbformat  # noqa: E402
from nbconvert.exporters.webpdf import WebPDFExporter  # noqa: E402

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

# Keeps wide markdown tables and long output lines inside the page.
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


class PrintReadyWebPDFExporter(WebPDFExporter):
    """WebPDF exporter with print CSS injected before Chromium renders."""

    def from_notebook_node(self, nb, resources=None, **kw):
        html, resources = super(WebPDFExporter, self).from_notebook_node(
            nb, resources=resources, **kw
        )
        html = html.replace("</head>", PRINT_CSS, 1)
        self.log.info("Building PDF")
        pdf_data = self.run_playwright(html)
        self.log.info("PDF successfully created")
        return pdf_data, resources


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    exporter = PrintReadyWebPDFExporter()
    ok = 0

    for name in NOTEBOOKS:
        src = os.path.join(REPO, name + ".ipynb")
        if not os.path.exists(src):
            print(f"SKIP  {name}: notebook not found")
            continue
        try:
            nb = nbformat.read(src, as_version=4)
            data, _ = exporter.from_notebook_node(nb)
            dest = os.path.join(OUT_DIR, name + ".pdf")
            with open(dest, "wb") as f:
                f.write(data)
            print(f"OK    {name}.pdf  ({len(data) // 1024} KB)")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")

    print(f"\n{ok} of {len(NOTEBOOKS)} notebooks converted.")
    print("Output folder:", OUT_DIR)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
