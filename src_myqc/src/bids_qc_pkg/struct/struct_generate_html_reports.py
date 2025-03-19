#!/usr/bin/env python3
import os
import re
import csv
import argparse

from flask import Flask, request, jsonify, send_file, abort, redirect

"""
Usage:
  python generate_html_reports.py /path/to/bids_root/results --phase initial
Then open your browser at http://127.0.0.1:5000

Changes from previous versions:
  - Regex now allows 'ses-6mo', 'ses-9mo', etc. (not just digits).
  - We parse each file individually, so multiple runs in the same directory are recognized.
  - We serve images/SVG via /get_image/<file_id> to avoid file:// issues.
  - The 'Run' label is shown in the HTML if present.
"""

app = Flask(__name__)

# Globals
PAGES = []                # list of all pages: each is (page_html, page_idx)
MASTER_CSV = "QC_data.csv"
PHASE = "initial"
FILE_MAP = {}             # int -> absolute filepath (for serving images)
FILE_ID_COUNTER = 0       # incremental ID for each file in FILE_MAP

@app.route("/")
def index():
    """
    Default route: go to the first page if it exists
    """
    if not PAGES:
        return "<h1>No reports found.</h1>"
    return redirect("/report/0")

@app.route("/report/<int:page_id>")
def show_report(page_id):
    """
    Show the page with index=page_id
    """
    if page_id < 0 or page_id >= len(PAGES):
        return "<h1>Invalid page index</h1>", 404
    page_html, _ = PAGES[page_id]
    return page_html

@app.route("/qc_update", methods=["POST"])
def qc_update():
    """
    AJAX endpoint to update the CSV for a given filename + status + notes
    """
    data = request.json
    filename = data.get("filename")
    status = data.get("status")
    notes = data.get("notes", "")
    if not filename or not status:
        return jsonify({"error": "Missing filename or status"}), 400

    update_csv(MASTER_CSV, filename, {"status": status, "notes": notes})
    return jsonify({"message": "QC updated successfully"})

@app.route("/get_image/<int:file_id>")
def get_image(file_id):
    """
    Serve an image or SVG from the absolute path stored in FILE_MAP.
    """
    if file_id not in FILE_MAP:
        abort(404, "File ID not found")
    abs_path = FILE_MAP[file_id]
    if not os.path.exists(abs_path):
        abort(404, f"File not found on disk: {abs_path}")

    # We'll guess the mimetype from extension
    ext = abs_path.lower()
    if ext.endswith(".png"):
        mimetype = "image/png"
    elif ext.endswith(".svg"):
        mimetype = "image/svg+xml"
    else:
        # fallback guess
        mimetype = "application/octet-stream"

    return send_file(abs_path, mimetype=mimetype)


def update_csv(csv_path, filename, status):
    """
    Load the CSV, update or append the row, write back.
    """
    rows = []
    found = False

    if os.path.exists(csv_path):
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)

    for r in rows:
        if r["filename"] == filename:
            r["status"] = status
            # Update notes only if provided in the status dict
            if isinstance(status, dict):
                r["notes"] = status.get("notes", r.get("notes", ""))
                r["status"] = status["status"]
            found = True
            break

    if not found:
        new_row = {"filename": filename}
        if isinstance(status, dict):
            new_row["status"] = status["status"]
            new_row["notes"] = status.get("notes", "")
        else:
            new_row["status"] = status
            new_row["notes"] = ""
        rows.append(new_row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "status", "notes"])
        writer.writeheader()
        writer.writerows(rows)

def main():
    parser = argparse.ArgumentParser(description="Generate HTML QC reports + local server.")
    parser.add_argument("root_dir", help="Top-level directory of results (usually BIDS_ROOT/results).")
    parser.add_argument("--phase", choices=["initial", "final"], default="initial",
                        help="Specify 'initial' or 'final' (optional). Affects the page title.")
    parser.add_argument("--csv", default="QC_data.csv",
                        help="Master CSV file to store QC statuses (default: QC_data.csv).")
    parser.add_argument("--port", default=8080, type=int,
                        help="Port for the local Flask server (default: 8080).")
    args = parser.parse_args()

    global PHASE
    global MASTER_CSV
    PHASE = args.phase
    MASTER_CSV = args.csv

    print(f"Scanning {args.root_dir} ...")
    generate_in_memory_pages(args.root_dir, phase=PHASE)
    print(f"Found {len(PAGES)} total pages (subject/session/run combos).")

    print(f"Launching local server on port {args.port}...")
    print(f"Open your browser at http://127.0.0.1:{args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)

def generate_in_memory_pages(root_dir, phase="initial"):
    """
    Walk the directory for all runs, store data in a dictionary keyed by (sub, ses, run).
    Then build an HTML page for each (sub, ses, run).
    """
    # Regex that captures: sub-XXXX_?ses-YYY_?run-ZZZ
    # allowing any characters (no underscore) after 'sub-', 'ses-', 'run-'.
    pattern = re.compile(r'(sub-[^_]+)(?:_(ses-[^_]+))?(?:_(run-[^_]+))?', re.IGNORECASE)

    data_map = {}  # (subject, session, run) -> dict with keys: orig, strip, dens, stats
    # We'll parse every single file individually
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)

            # Check what type of file
            if not any(x in fname for x in ["_original_slices.png",
                                            "_skullstripped_slices.png",
                                            "_density.svg",
                                            "_stats.csv",
                                            "T1w.nii.gz"]):
                continue  # skip irrelevant files

            # Attempt to parse sub/ses/run
            match = pattern.search(fname)
            if not match:
                # If we can't parse, skip or store in a "misc" group if you like
                continue

            subject = match.group(1)  # e.g. sub-011228
            session = match.group(2) if match.group(2) else 'ses-01'
            run     = match.group(3) if match.group(3) else ''   # e.g. run-001

            key = (subject, session, run)
            if key not in data_map:
                data_map[key] = {
                    "orig": None,
                    "strip": None,
                    "dens": None,
                    "stats": None
                }

            # Assign the file path to the correct slot
            if fname.endswith("_original_slices.png"):
                data_map[key]["orig"] = fullpath
            elif fname.endswith("_skullstripped_slices.png"):
                data_map[key]["strip"] = fullpath
            elif fname.endswith("_density.svg"):
                data_map[key]["dens"] = fullpath
            elif fname.endswith("_stats.csv"):
                data_map[key]["stats"] = fullpath

    # Now build pages for each key
    # Sort them by numeric approach if you want (like sub-011228 => sub, ses => etc.)
    def numeric_sort_key(k):
        subject, session, run = k
        # parse any digits from subject
        # if user has sub-011228, we'll do "011228"
        sub_num = parse_int(subject.replace("sub-", ""))
        ses_num = parse_int(session.replace("ses-", ""))
        run_num = parse_int(run.replace("run-", ""))
        return (sub_num, ses_num, run_num)

    sorted_keys = sorted(data_map.keys(), key=numeric_sort_key)

    # clear global
    PAGES.clear()
    FILE_MAP.clear()
    global FILE_ID_COUNTER
    FILE_ID_COUNTER = 0

    # Build one page per key
    for idx, key in enumerate(sorted_keys):
        subject, session, run = key
        files_info = data_map[key]

        page_html = build_html_page(subject, session, run, files_info, phase, idx, len(sorted_keys))
        PAGES.append((page_html, idx))

def build_html_page(subject, session, run, files_info, phase, page_id, total_pages):
    """
    Build the actual HTML content for a single (sub, ses, run).
    We'll use /get_image/<file_id> routes to serve images.
    """
    # prev/next
    prev_id = page_id - 1
    next_id = page_id + 1
    if prev_id >= 0:
        prev_link = f'<a href="/report/{prev_id}">Previous</a>'
    else:
        prev_link = '<span style="color:gray;">Previous</span>'
    if next_id < total_pages:
        next_link = f'<a href="/report/{next_id}">Next</a>'
    else:
        next_link = '<span style="color:gray;">Next</span>'

    orig_html  = embed_png(files_info["orig"],  "Original Slices")       if files_info["orig"]  else not_found("Original Slices")
    strip_html = embed_png(files_info["strip"], "Skull-Stripped Slices") if files_info["strip"] else not_found("Skull-Stripped Slices")
    dens_html  = embed_svg(files_info["dens"],  "Density Plot")          if files_info["dens"]  else not_found("Density Plot")
    stats_html = embed_stats(files_info["stats"])                        if files_info["stats"] else not_found("Stats")

    # We'll pick a single "filename" key to represent this page in the CSV.
    # Typically, you'd want to store sub-ses-run in the CSV, or the original_slices path.
    # We'll store just the "orig" path's basename if present, else something else:
    csv_filename_key = None
    if files_info["orig"]:
        csv_filename_key = os.path.basename(files_info["orig"])
    elif files_info["strip"]:
        csv_filename_key = os.path.basename(files_info["strip"])
    elif files_info["dens"]:
        csv_filename_key = os.path.basename(files_info["dens"])
    elif files_info["stats"]:
        csv_filename_key = os.path.basename(files_info["stats"])
    else:
        # fallback
        csv_filename_key = f"{subject}_{session}_{run}"

    # Build the HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>{subject} {session} {run} Report ({phase})</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
        }}
        .nav {{
            margin-bottom: 20px;
        }}
        .nav span, .nav a {{
            margin-right: 20px;
            font-weight: bold;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .png-image, .svg-image {{
            max-width: 90%;
            border: 1px solid #ccc;
            margin-bottom: 10px;
            display: block;
            position: relative;
        }}
        .stats-table {{
            border-collapse: collapse;
            margin-top: 10px;
        }}
        .stats-table td, .stats-table th {{
            border: 1px solid #999;
            padding: 6px 10px;
        }}
        .annotation-container {{
            position: relative;
            display: inline-block;
        }}
        .annot-canvas {{
            position: absolute;
            top: 0;
            left: 0;
            border: 1px solid #ccc;
            opacity: 0.6;
        }}
        .qc-buttons {{
            margin: 20px 0;
        }}
        .qc-buttons button {{
            margin-right: 10px;
            padding: 8px 12px;
            font-size: 14px;
            cursor: pointer;
        }}
        .qc-status {{
            font-weight: bold;
            margin-left: 20px;
        }}
    </style>
</head>
<body>

<div class="nav">
    {prev_link} {next_link}
</div>

<h2>Subject: {subject} | Session: {session} | Run: {run} | Phase: {phase}</h2>

<div class="qc-buttons">
    <button onclick="markQC('GOOD')">Good</button>
    <button onclick="markQC('BAD')">Bad</button>
    <button onclick="markQC('UNCLEAR')">Unclear</button>
    <span class="qc-status" id="qcStatusDisplay">Status: UNKNOWN</span>
    <label for="qcNotes" style="margin-left: 20px;">Notes:</label>
    <input type="text" id="qcNotes" style="width: 200px; margin-left: 5px; padding: 5px;" onchange="saveNotes()" placeholder="Add notes here..."/>
</div>

<div class="section">
    {orig_html}
</div>
<div class="section">
    {strip_html}
</div>
<div class="section">
    {dens_html}
</div>
<div class="section">
    {stats_html}
</div>

<script>
function markQC(status) {{
    document.getElementById('qcStatusDisplay').innerText = "Status: " + status;
    const notes = document.getElementById('qcNotes').value;
    fetch("/qc_update", {{
        method: "POST",
        headers: {{
            "Content-Type": "application/json"
        }},
        body: JSON.stringify({{ filename: "{csv_filename_key}", status: status, notes: notes }})
    }})
    .then(r => r.json())
    .then(d => console.log(d))
    .catch(err => console.error("Error:", err));
}}

// For each annotation container, freehand drawing
document.addEventListener('DOMContentLoaded', function() {{
    const containers = document.querySelectorAll('.annotation-container');
    containers.forEach(container => {{
        const canvas = container.querySelector('.annot-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let drawing = false;
        function startDraw(e) {{
            drawing = true;
            ctx.beginPath();
            ctx.moveTo(e.offsetX, e.offsetY);
        }}
        function draw(e) {{
            if (!drawing) return;
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.strokeStyle = 'red';
            ctx.lineTo(e.offsetX, e.offsetY);
            ctx.stroke();
        }}
        function endDraw(e) {{
            drawing = false;
        }}
        canvas.addEventListener('mousedown', startDraw);
        canvas.addEventListener('mousemove', draw);
        canvas.addEventListener('mouseup', endDraw);
        canvas.addEventListener('mouseleave', endDraw);
    }});
}});
</script>

</body>
</html>
"""
    return html


##############################################################################
# Serving & Embedding Helpers
##############################################################################

def embed_png(abs_path, title="Image"):
    """
    Store abs_path in FILE_MAP, return an <img> referencing /get_image/<id>.
    """
    if not abs_path:
        return not_found(title)
    file_id = store_file(abs_path)
    return f"""
    <h3>{title}</h3>
    <div class="annotation-container">
        <img class="png-image" src="/get_image/{file_id}" onload="resizeCanvas(this)" />
        <canvas class="annot-canvas"></canvas>
    </div>
    <script>
    function resizeCanvas(imgElem) {{
        let canvas = imgElem.parentNode.querySelector('.annot-canvas');
        if (canvas) {{
            canvas.width = imgElem.width;
            canvas.height = imgElem.height;
        }}
    }}
    </script>
    """

def embed_svg(abs_path, title="Image"):
    """
    Store abs_path in FILE_MAP, return an <object> referencing /get_image/<id>.
    """
    if not abs_path:
        return not_found(title)
    file_id = store_file(abs_path)
    return f"""
    <h3>{title}</h3>
    <div class="annotation-container">
        <object class="svg-image" type="image/svg+xml" data="/get_image/{file_id}" onload="resizeSvgCanvas(this)"></object>
        <canvas class="annot-canvas"></canvas>
    </div>
    <script>
    function resizeSvgCanvas(objElem) {{
        let canvas = objElem.parentNode.querySelector('.annot-canvas');
        if (canvas) {{
            // You can refine logic to match the rendered size of the SVG
            canvas.width = 600;
            canvas.height = 400;
        }}
    }}
    </script>
    """

def not_found(title="Item"):
    return f"<h3>{title}</h3><p style='color:red;'>No file found.</p>"

def embed_stats(abs_path):
    """
    Minimal approach: parse first line(s) for mean, median, max, min, std
    """
    if not abs_path:
        return not_found("Stats")
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        if len(lines) == 0:
            return "<h3>Stats</h3><p>Empty CSV</p>"
        # If there's a header, second line is numeric
        parts = None
        if len(lines) >= 2 and all_numeric(lines[1].split(',')):
            parts = lines[1].split(',')
        else:
            parts = lines[0].split(',')

        if len(parts) != 5:
            return f"<h3>Stats</h3><p>Expected 5 columns, found {len(parts)}. CSV: {abs_path}</p>"
        # mean, median, max, min, std
        return f"""
        <h3>Statistics</h3>
        <p>Mean: {parts[0]}, Median: {parts[1]}, Max: {parts[2]}, Min: {parts[3]}, Std: {parts[4]}</p>
        """
    except Exception as e:
        return f"<h3>Stats</h3><p>Error reading CSV: {e}</p>"

def all_numeric(vals):
    try:
        for v in vals:
            float(v)
        return True
    except ValueError:
        return False

def store_file(abs_path):
    """
    Adds abs_path to FILE_MAP with a new integer ID, returns that ID.
    """
    global FILE_ID_COUNTER
    FILE_MAP[FILE_ID_COUNTER] = abs_path
    this_id = FILE_ID_COUNTER
    FILE_ID_COUNTER += 1
    return this_id

def parse_int(s):
    """
    Extract an integer from a string like '6mo' or '001'. If we can't parse, return 0.
    """
    # e.g. "001" -> 1, "6mo" -> 6 (if you want), else fallback 0
    # This is a naive approach. Adapt if you prefer a more robust parse.
    import re
    m = re.search(r'(\d+)', s)
    if m:
        return int(m.group(1))
    return 0

if __name__ == "__main__":
    main()