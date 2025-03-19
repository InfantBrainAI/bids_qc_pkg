#!/usr/bin/env python3
import os
import re
import argparse

def main():
    """
    Command-line entry point for generating HTML QC reports.
    Example usage:
        bids-qc-report /path/to/bids_root/results --phase initial
        bids-qc-report /path/to/bids_root/results --phase final
    """
    parser = argparse.ArgumentParser(description="Generate HTML QC reports.")
    parser.add_argument("root_dir", help="Top-level directory of results (usually BIDS_ROOT/results).")
    parser.add_argument("--phase", choices=["initial", "final"], default="initial",
                        help="Specify 'initial' or 'final' (optional). Affects HTML filename & header.")
    args = parser.parse_args()

    generate_html_reports(args.root_dir, phase=args.phase)

def generate_html_reports(root_dir, phase="initial"):
    """
    root_dir: The top-level directory containing 'sub-XXXX' folders (with results).
    Walk the directory tree to find:
      - *_original_slices.png
      - *_skullstripped_slices.png
      - *_density.svg
      - *_stats.csv

    Then produce an HTML report for each (sub, ses).
    If phase='initial', we name the report "sub-XXX_ses-YYY_T1w_report_initial.html"
    If phase='final', we name it "sub-XXX_ses-YYY_T1w_report_final.html"
    """
    data_map = {}
    pattern = re.compile(r'(sub-\d+)_?(ses-\d+)?')
    print(f"Walking {root_dir}")
    for dirpath, _, filenames in os.walk(root_dir):
        print(f"Walking {dirpath}")
        orig_file = None
        strip_file = None
        dens_file = None
        stats_file = None

        for fname in filenames:
            fullpath = os.path.join(dirpath, fname)
            if fname.endswith('_original_slices.png'):
                orig_file = fullpath
            elif fname.endswith('_skullstripped_slices.png'):
                strip_file = fullpath
            elif fname.endswith('_density.svg'):
                dens_file = fullpath
            elif fname.endswith('_stats.csv'):
                stats_file = fullpath

        # If at least one relevant file was found, figure out subject/session
        candidate_file = orig_file or strip_file or dens_file or stats_file
        if candidate_file:
            match = pattern.search(os.path.basename(candidate_file))
            if match:
                subject = match.group(1)  # e.g. sub-002081
                session = match.group(2) if match.group(2) else 'ses-01'

                key = (subject, session)
                if key not in data_map:
                    data_map[key] = {
                        "orig": None,
                        "strip": None,
                        "dens": None,
                        "stats": None,
                        "directory": dirpath
                    }

                if orig_file:
                    data_map[key]["orig"] = orig_file
                if strip_file:
                    data_map[key]["strip"] = strip_file
                if dens_file:
                    data_map[key]["dens"] = dens_file
                if stats_file:
                    data_map[key]["stats"] = stats_file

    # Sort the (subject, session) keys by numeric value
    def numeric_sort_key(k):
        sub_str, ses_str = k
        # handle case if session is missing or something
        sub_num = int(sub_str.replace('sub-', ''))
        ses_num = 1
        if ses_str and ses_str.startswith('ses-'):
            ses_num = int(ses_str.replace('ses-', ''))
        return (sub_num, ses_num)

    sorted_keys = sorted(data_map.keys(), key=numeric_sort_key)

    key_html_paths = []
    for key in sorted_keys:
        subject, session = key
        out_dir = data_map[key]["directory"]
        # Differentiate the HTML name by phase
        report_name = f"{subject}_{session}_T1w_report_{phase}.html"
        if session == 'ses-01':
            # In case session is missing in the filename, do what you need
            report_name = f"{subject}_T1w_report_{phase}.html"
        html_path = os.path.join(out_dir, report_name)
        key_html_paths.append((key, html_path))
    print(f"Generated {len(key_html_paths)} HTML reports")
    for i, (key, html_path) in enumerate(key_html_paths):
        subject, session = key
        files_info = data_map[key]

        # Build Prev/Next links
        if i > 0:
            _, prev_html = key_html_paths[i-1]
            rel_prev = os.path.relpath(prev_html, os.path.dirname(html_path))
            prev_link = f'<a href="{rel_prev}">Previous</a>'
        else:
            prev_link = '<span style="color:gray;">Previous</span>'

        if i < len(key_html_paths) - 1:
            _, next_html = key_html_paths[i+1]
            rel_next = os.path.relpath(next_html, os.path.dirname(html_path))
            next_link = f'<a href="{rel_next}">Next</a>'
        else:
            next_link = '<span style="color:gray;">Next</span>'

        # Prepare embedded blocks
        orig_png  = embed_png(files_info["orig"],  "Original Slices")       if files_info["orig"]  else not_found("Original Slices")
        strip_png = embed_png(files_info["strip"], "Skull-Stripped Slices") if files_info["strip"] else not_found("Skull-Stripped Slices")
        dens_svg  = embed_svg(files_info["dens"],  "Density Plot")          if files_info["dens"]  else not_found("Density Plot")
        stats_tbl = embed_stats(files_info["stats"])                        if files_info["stats"] else not_found("Stats")

        # Assemble HTML with annotation tool + Good/Bad classification
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>{subject} {session} Report ({phase})</title>
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
        /* Annotation canvas overlay */
        .annotation-container {{
            position: relative;
            display: inline-block;
        }}
        .annot-canvas {{
            position: absolute;
            top: 0;
            left: 0;
            border: 1px solid #ccc;
            opacity: 0.6;  /* Adjust transparency as needed */
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

    <!-- Navigation -->
    <div class="nav">
        {prev_link} {next_link}
    </div>

    <h2>Subject: {subject} | Session: {session} | Phase: {phase}</h2>

    <div class="qc-buttons">
        <button onclick="markQC('GOOD')">Mark Good</button>
        <button onclick="markQC('BAD')">Mark Bad</button>
        <button onclick="markQC('UNCLEAR')">Mark Unclear</button>
        <span class="qc-status" id="qcStatusDisplay">Status: UNKNOWN</span>
        <label for="qcNotes" style="margin-left: 20px;">Notes:</label>
        <input type="text" id="qcNotes" style="width: 200px; margin-left: 5px; padding: 5px;" onchange="saveNotes()" placeholder="Add notes here..."/>
    </div>

    <div class="section">
        {orig_png}
    </div>

    <div class="section">
        {strip_png}
    </div>

    <div class="section">
        {dens_svg}
    </div>

    <div class="section">
        {stats_tbl}
    </div>

    <!-- Minimal annotation JavaScript snippet -->
    <script>
    // For each annotation container:
    // We attach an event listener to the canvas to allow freehand drawing.
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

        // On load, retrieve stored QC status and notes from localStorage
        loadQCStatus();
        loadNotes();
    }});

    // Store Good/Bad/Unclear decision in localStorage
    function markQC(status) {{
        const subject = "{subject}";
        const session = "{session}";
        const phase   = "{phase}";
        const key = `QC_${{subject}}_${{session}}_${{phase}}`;
        localStorage.setItem(key, status);
        document.getElementById('qcStatusDisplay').innerHTML = `Status: ${{status}}`;
        
        // Save notes along with the status
        saveNotes();
    }}

    // Save notes to localStorage
    function saveNotes() {{
        const subject = "{subject}";
        const session = "{session}";
        const phase   = "{phase}";
        const notes = document.getElementById('qcNotes').value;
        const notesKey = `QC_NOTES_${{subject}}_${{session}}_${{phase}}`;
        localStorage.setItem(notesKey, notes);
    }}

    // On page load, display the previously selected QC status
    function loadQCStatus() {{
        const subject = "{subject}";
        const session = "{session}";
        const phase   = "{phase}";
        const key = `QC_${{subject}}_${{session}}_${{phase}}`;
        const storedValue = localStorage.getItem(key);
        if (storedValue) {{
            document.getElementById('qcStatusDisplay').innerHTML = `Status: ${{storedValue}}`;
        }}
    }}

    // On page load, load any previously saved notes
    function loadNotes() {{
        const subject = "{subject}";
        const session = "{session}";
        const phase   = "{phase}";
        const notesKey = `QC_NOTES_${{subject}}_${{session}}_${{phase}}`;
        const storedNotes = localStorage.getItem(notesKey);
        if (storedNotes) {{
            document.getElementById('qcNotes').value = storedNotes;
        }}
    }}
    </script>

</body>
</html>"""

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    print("HTML reports generated successfully!")

def embed_png(png_path, title="Image"):
    """
    Return an HTML snippet that displays the PNG with a canvas overlay for annotations.
    """
    if not png_path:
        return not_found(title)
    fname = os.path.basename(png_path)
    return f"""
    <h3>{title}</h3>
    <div class="annotation-container">
        <img class="png-image" src="{fname}" onload="resizeCanvas(this)" />
        <canvas class="annot-canvas"></canvas>
    </div>
    <script>
    // Resize the canvas to match the image dimensions
    function resizeCanvas(imgElem) {{
        let canvas = imgElem.parentNode.querySelector('.annot-canvas');
        if (canvas) {{
            canvas.width = imgElem.width;
            canvas.height = imgElem.height;
        }}
    }}
    </script>
    """

def embed_svg(svg_path, title="Image"):
    """
    Return an HTML snippet that displays the SVG with a canvas overlay for annotations.
    """
    if not svg_path:
        return not_found(title)
    fname = os.path.basename(svg_path)
    return f"""
    <h3>{title}</h3>
    <div class="annotation-container">
        <!-- For an SVG, we embed it in an <object> or <img> -->
        <object class="svg-image" type="image/svg+xml" data="{fname}" onload="resizeSvgCanvas(this)"></object>
        <canvas class="annot-canvas"></canvas>
    </div>
    <script>
    // Rough approach to resizing the canvas after the SVG loads
    function resizeSvgCanvas(objElem) {{
        let canvas = objElem.parentNode.querySelector('.annot-canvas');
        if (canvas) {{
            // We can't easily get the rendered width/height of an <object> with an SVG,
            // so you might want a more robust approach or fixed size.
            canvas.width = 600;
            canvas.height = 400;
        }}
    }}
    </script>
    """

def not_found(title="Item"):
    """
    Return a simple HTML snippet indicating a missing file.
    """
    return f"<h3>{title}</h3><p style='color:red;'>No file found.</p>"

def embed_stats(csv_path):
    """
    Reads a CSV expecting columns: mean, median, max, min, std
    on a single line (or second line if first line is header).
    Produces a small HTML table.
    """
    if not csv_path:
        return not_found("Stats")
    fname = os.path.basename(csv_path)
    headers = ["mean", "median", "max", "min", "std"]

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            if len(lines) >= 2 and all_numeric(lines[1].split(',')):
                data_line = lines[1]
            else:
                data_line = lines[0]

            values = data_line.split(',')
    except Exception as e:
        return f"<h3>Stats</h3><p>Unable to read CSV: {e}</p>"

    if len(values) != 5:
        return f"""
        <h3>Stats</h3>
        <p>Unexpected format: found {len(values)} columns instead of 5.</p>
        <p><a href="{fname}" download>Download CSV</a></p>
        """

    table_html = f"""
    <h3>Statistics</h3>
    <table class="stats-table">
      <tr>{"".join(f"<th>{h}</th>" for h in headers)}</tr>
      <tr>{"".join(f"<td>{val}</td>" for val in values)}</tr>
    </table>
    <p><a href="{fname}" download>Download CSV</a></p>
    """
    return table_html

def all_numeric(vals):
    """
    Helper to check if every item in `vals` can be cast to float.
    """
    try:
        for v in vals:
            float(v)
        return True
    except ValueError:
        return False