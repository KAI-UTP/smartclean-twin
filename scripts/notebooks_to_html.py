"""Export the notebooks to standalone, print-ready HTML files.

Open any of the generated files in Chrome and press Ctrl+P: the whole notebook
paginates correctly, with no Jupyter menus and no clipped tables.

Run with MAKE-PRINTABLE-HTML.bat, or:
    py scripts\\notebooks_to_html.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

REPO = r"D:\UTP\UG Y2S3\03 Digital Twin\smartclean-twin"
OUT_DIR = r"D:\UTP\UG Y2S3\03 Digital Twin\printable-html"

NOTEBOOKS = [
    "submission_1_visualization",
    "submission_2_ai_model",
    "submission_3_data_streaming",
    "submission_4_dev_practices",
    "submission_5_deployment",
    "project_walkthrough",
]

PRINT_CSS = """
<style>
@page { size: A4 portrait; margin: 11mm; }
@media print {
  body { font-size: 10pt; }
  .jp-Cell, .jp-OutputArea-output, .jp-Notebook { overflow: visible !important; }
  .jp-Cell { page-break-inside: avoid; }
}
body { font-size: 10.5pt; }
.jp-RenderedHTMLCommon table, table {
  width: 100% !important; table-layout: auto !important;
  font-size: 8.5pt !important; border-collapse: collapse;
}
.jp-RenderedHTMLCommon th, .jp-RenderedHTMLCommon td, th, td {
  white-space: normal !important; overflow-wrap: break-word !important;
  padding: 3px 5px !important; max-width: none !important;
  border: 1px solid #ccc;
}
pre, code, .jp-OutputArea-output pre {
  white-space: pre-wrap !important; overflow-wrap: break-word !important;
  font-size: 7.5pt !important;
}
</style>
</head>"""


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="nb2html_")
    ok = 0

    for name in NOTEBOOKS:
        ipynb = os.path.join(REPO, name + ".ipynb")
        if not os.path.exists(ipynb):
            print(f"SKIP  {name}: notebook not found")
            continue

        subprocess.run(
            [sys.executable, "-m", "jupyter", "nbconvert", "--to", "html",
             "--output-dir", tmp, ipynb],
            capture_output=True, text=True,
        )
        html = os.path.join(tmp, name + ".html")
        if not os.path.exists(html):
            print(f"FAIL  {name}")
            continue

        with open(html, encoding="utf-8") as f:
            content = f.read()
        content = content.replace("</head>", PRINT_CSS, 1)
        dest = os.path.join(OUT_DIR, name + ".html")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"OK    {name}.html  ({os.path.getsize(dest) // 1024} KB)")
        ok += 1

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{ok} of {len(NOTEBOOKS)} exported.")
    print("Folder:", OUT_DIR)
    print("\nTo print: open a .html file in Chrome, press Ctrl+P,")
    print("choose Save as PDF, and tick Background graphics under More settings.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
