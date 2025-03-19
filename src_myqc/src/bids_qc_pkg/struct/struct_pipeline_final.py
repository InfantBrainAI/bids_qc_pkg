import os
import sys
import logging
import argparse

import numpy as np
import nibabel as nib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)

###############################################################################
# Skull Stripping
###############################################################################
def ensure_docker_image():
    """
    Check if the SynthStrip Docker image exists locally, and pull it if not.
    Returns True if image is available (either existed or successfully pulled),
    False otherwise.
    """
    try:
        # Check if image exists locally
        check_cmd = "docker images -q freesurfer/synthstrip:latest"
        image_exists = os.system(check_cmd) == 0 and os.popen(check_cmd).read().strip() != ""
        
        if not image_exists:
            logger.info("SynthStrip Docker image not found locally. Pulling from Docker Hub...")
            pull_cmd = "docker pull --platform linux/amd64 freesurfer/synthstrip:latest"
            if os.system(pull_cmd) != 0:
                logger.error("Failed to pull SynthStrip Docker image")
                return False
            logger.info("Successfully pulled SynthStrip Docker image")
        
        return True
    except Exception as e:
        logger.error(f"Error checking/pulling Docker image: {str(e)}")
        return False

def process_skull_stripping(filepath):
    """
    Perform skull stripping using SynthStrip Docker container and save the output 
    in the same directory as the original file.

    Returns:
        str or None: Path to the skull-stripped NIfTI file, or None if an error occurred.
    """
    try:
        # Ensure Docker image is available
        if not ensure_docker_image():
            logger.error("Could not ensure Docker image availability")
            return None

        # Remove double extension for .nii.gz vs .nii
        base_no_ext = os.path.splitext(os.path.splitext(filepath)[0])[0]
        output_path = f"{base_no_ext}_skullstripped.nii.gz"

        # Build the Docker command
        abs_filepath = os.path.abspath(filepath)
        parent_dir = os.path.dirname(abs_filepath)
        filename = os.path.basename(abs_filepath)
        stripped_filename = os.path.basename(output_path)

        cmd = f"""
        docker run --platform linux/amd64 \
        -v "{parent_dir}":/data \
        freesurfer/synthstrip:latest \
        -i /data/{filename} \
        -o /data/{stripped_filename}
        """

        logger.info(f"Running SynthStrip on {filepath}...")
        exit_code = os.system(cmd)
        if exit_code != 0:
            logger.error(f"Skull stripping failed with exit code {exit_code}")
            return None

        return output_path

    except Exception as e:
        logger.error(f"process_skull_stripping failed for {filepath}: {str(e)}")
        return None

###############################################################################
# Slice Selection & Plotting
###############################################################################
import numpy as np

def find_slices_of_interest(data, num_slices=10):
    """
    1) Find the single slice with the highest sum of intensities (best_idx).
    2) Create a bounding region [start_idx, end_idx] around best_idx.
    3) Use np.linspace to pick num_slices slices evenly spaced in that region.
    
    Returns up to num_slices slices (clamped to image boundaries).
    """
    slice_sums = np.sum(data, axis=(0, 1))
    best_idx = np.argmax(slice_sums)

    # We'll define a margin to pick from best_idx-margin to best_idx+margin
    margin = num_slices * 5
    zsize = data.shape[2]

    start_idx = max(0, best_idx - margin)
    end_idx = min(zsize - 1, best_idx + margin)

    # If there's enough space, we could expand the region to ensure 
    # we can spread slices out more. For instance, you can define 
    # a bigger margin if you'd like. But for now, let's keep it simple.

    # Use np.linspace to generate 'num_slices' points from start_idx to end_idx.
    # Convert them to integers. 
    slice_indices = np.linspace(start_idx, end_idx, num_slices, dtype=int)

    # Ensure unique and sorted (linspace might create duplicates if the range is small)
    slice_indices = np.unique(slice_indices)
    return slice_indices


def plot_slices(data, slice_indices, output_path, title="", nrows=5, ncols=2):
    """
    Plot specified axial slice indices of a 3D volume in a grid (nrows x ncols)
    and save as an SVG.

    Args:
        data (np.ndarray): 3D image data
        slice_indices (list or np.ndarray): Indices of slices to plot
        output_path (str): Output file path for saving the figure
        title (str): A title for the figure
        nrows (int): Number of rows in the subplot grid
        ncols (int): Number of columns in the subplot grid
    """
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(4*ncols, 4*nrows))
    for i, ax in enumerate(axes.flat):
        if i < len(slice_indices):
            idx = slice_indices[i]
            slice_data = data[:, :, idx].T  # transpose for correct orientation
            # Flip up-down so slice 0 is at bottom
            ax.imshow(np.flipud(slice_data), cmap='gray', origin='lower')
            ax.set_title(f"Slice {idx}")
            ax.axis('off')
        else:
            ax.axis('off')

    plt.suptitle(title)
    plt.tight_layout()
    plt.savefig(output_path, format='png', bbox_inches='tight')
    plt.close(fig)

###############################################################################
# Analysis
###############################################################################
def analyze_nifti(filepath):
    """
    Load a NIfTI file, compute basic intensity stats, and return them as a dict.

    Returns:
        dict: {mean, median, max, min, std} or empty dict on error
    """
    try:
        img = nib.load(filepath)
        data = img.get_fdata()

        stats = {
            'mean': float(np.mean(data)),
            'median': float(np.median(data)),
            'max': float(np.max(data)),
            'min': float(np.min(data)),
            'std': float(np.std(data))
        }
        return stats
    except Exception as e:
        logger.error(f"analyze_nifti failed for {filepath}: {str(e)}")
        return {}

def create_density_plot_and_save(data, output_path, title=""):
    """
    Create a density (KDE) plot of voxel intensities and save it to SVG.
    """
    plt.figure(figsize=(10, 6))
    sns.kdeplot(data=data.flatten(), shade=False)
    plt.title(title)
    plt.xlabel("Image Intensity")
    plt.ylabel("Density")
    plt.savefig(output_path, format='svg', bbox_inches='tight')
    plt.close()


def process_scan_final(bids_root, filepath, num_slices=10):
    """
    Final pass: Perform skull-stripping and produce original vs stripped slices, stats, etc.
    """
    base_no_ext = os.path.splitext(os.path.splitext(os.path.basename(filepath))[0])[0]
    logger.info(f"[Final QC] Processing {filepath} ...")

    # 1) If skull-stripped file doesn't exist, run it
    stripped_filename = f"{base_no_ext}_skullstripped.nii.gz"
    stripped_path = os.path.join(os.path.dirname(filepath), stripped_filename)

    if os.path.exists(stripped_path):
        logger.info(f"Found existing skull-stripped file: {stripped_path}")
    else:
        if not ensure_docker_image():
            logger.error("Could not ensure Docker image availability. Skipping.")
            return

        logger.info(f"No skull-stripped file found. Running skull stripping on {filepath}...")
        result_path = process_skull_stripping(filepath)
        if not result_path or not os.path.exists(result_path):
            logger.warning(f"No skull-stripped file produced for {filepath}. Skipping further analysis.")
            return
        stripped_path = result_path

    # 2) Load stripped data & find slices
    stripped_img = nib.load(stripped_path)
    stripped_data = stripped_img.get_fdata()
    slice_indices = find_slices_of_interest(stripped_data, num_slices=num_slices)

    # 3) Plot & save slices to results folder
    results_dir = ensure_results_dir(bids_root, filepath)
    stripped_png = os.path.join(results_dir, f"{base_no_ext}_skullstripped_slices.png")
    original_png = os.path.join(results_dir, f"{base_no_ext}_original_slices.png")

    plot_slices(
        stripped_data,
        slice_indices,
        stripped_png,
        title=f"{base_no_ext} - Skull Stripped",
        nrows=2,
        ncols=5
    )

    original_data = nib.load(filepath).get_fdata()
    plot_slices(
        original_data,
        slice_indices,
        original_png,
        title=f"{base_no_ext} - Original",
        nrows=2,
        ncols=5
    )

    # 4) Stats & density for original
    intensity_stats = analyze_nifti(filepath)
    if intensity_stats:
        stats_csv_path = os.path.join(results_dir, f"{base_no_ext}_stats.csv")
        pd.DataFrame([intensity_stats]).to_csv(stats_csv_path, index=False)

        density_svg_path = os.path.join(results_dir, f"{base_no_ext}_density.svg")
        create_density_plot_and_save(
            original_data,
            density_svg_path,
            title=f"Density Plot - {base_no_ext}"
        )

    logger.info(f"[Final QC] Finished processing {filepath}.\n")

def traverse_bids_final(bids_root, accepted_csv, scan_type="T1w", num_slices=10):
    """
    Only process scans that appear in accepted_csv. 
    """
    logger.info(f"[Final QC] Starting traversal of {bids_root} for scan type {scan_type}...")

    # 1) Load accepted subject/session IDs into a set
    accepted = load_accepted_csv(accepted_csv)

    for root, dirs, files in os.walk(bids_root):
        if "results" in root:
            continue

        for fname in files:
            if (fname.endswith(".nii") or fname.endswith(".nii.gz")) and (scan_type in fname):
                # Check if sub/ses is in the accepted set
                # We'll parse sub-XXXX_ses-YYYY from the fname or from the path
                # This depends on your naming. Example approach:
                fullpath = os.path.join(root, fname)
                sub_ses_key = extract_sub_ses(fullpath)

                if sub_ses_key in accepted:
                    process_scan_final(bids_root, fullpath, num_slices=num_slices)
                else:
                    logger.info(f"Skipping {fullpath} (not in accepted list).")

    logger.info("[Final QC] Finished processing all files.")

def load_accepted_csv(csv_path):
    """
    CSV with lines like:
       subject_id, session_id
       sub-001, ses-01
       sub-002, ses-02
    Returns a set of (sub-001, ses-01), ...
    """
    df = pd.read_csv(csv_path)
    accepted_set = set()
    for _, row in df.iterrows():
        accepted_set.add((row['subject_id'], row['session_id']))
    return accepted_set

def extract_sub_ses(filepath):
    """
    Simple function to parse sub-XXXX_ses-YYYY from filepath or basename.
    Adjust to your naming scheme. 
    """
    basename = os.path.basename(filepath)
    # For instance, you can do:
    # sub-1234_ses-2_T1w.nii.gz -> (sub-1234, ses-2)
    import re
    pattern = re.compile(r'(sub-\d+)_?(ses-\d+)?')
    m = pattern.search(basename)
    if m:
        sub_id = m.group(1)
        ses_id = m.group(2) or 'ses-01'
        return (sub_id, ses_id)
    else:
        # fallback if not found
        return (None, None)

def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Final QC pipeline (skull stripping).")
    parser.add_argument("bids_root", help="Path to the BIDS root directory")
    parser.add_argument("accepted_csv", help="CSV with subject/session IDs to process")
    parser.add_argument("scan_type", help="Scan type substring to match, e.g. T1w or T2w")
    parser.add_argument("--num_slices", type=int, default=10, 
                        help="Number of slices to display (default: 10)")
    args = parser.parse_args()

    traverse_bids_final(args.bids_root, args.accepted_csv, scan_type=args.scan_type, num_slices=args.num_slices)