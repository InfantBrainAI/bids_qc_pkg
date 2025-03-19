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


def find_slices_of_interest(data, num_slices=10):
    slice_sums = np.sum(data, axis=(0, 1))
    best_idx = np.argmax(slice_sums)
    margin = num_slices * 5
    zsize = data.shape[2]
    start_idx = max(0, best_idx - margin)
    end_idx = min(zsize - 1, best_idx + margin)
    slice_indices = np.linspace(start_idx, end_idx, num_slices, dtype=int)
    return np.unique(slice_indices)

def plot_slices(data, slice_indices, output_path, title="", nrows=5, ncols=2):
    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(4*ncols, 4*nrows))
    for i, ax in enumerate(axes.flat):
        if i < len(slice_indices):
            idx = slice_indices[i]
            slice_data = data[:, :, idx].T
            ax.imshow(np.flipud(slice_data), cmap='gray', origin='lower')
            ax.set_title(f"Slice {idx}")
            ax.axis('off')
        else:
            ax.axis('off')
    plt.suptitle(title)
    plt.tight_layout()
    plt.savefig(output_path, format='png', bbox_inches='tight')
    plt.close(fig)

def ensure_results_dir(bids_root, filepath):
    rel_path = os.path.relpath(os.path.dirname(filepath), bids_root)
    results_dir = os.path.join(bids_root, "results", rel_path)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def analyze_nifti(filepath):
    try:
        img = nib.load(filepath)
        data = img.get_fdata()
        return {
            'mean': float(np.mean(data)),
            'median': float(np.median(data)),
            'max': float(np.max(data)),
            'min': float(np.min(data)),
            'std': float(np.std(data))
        }
    except Exception as e:
        logger.error(f"analyze_nifti failed for {filepath}: {str(e)}")
        return {}

def create_density_plot_and_save(data, output_path, title=""):
    plt.figure(figsize=(10, 6))
    sns.kdeplot(data=data.flatten(), fill=False)
    plt.title(title)
    plt.xlabel("Image Intensity")
    plt.ylabel("Density")
    plt.savefig(output_path, format='svg', bbox_inches='tight')
    plt.close()

def strip_nii_gz(basename):
    if basename.endswith(".nii.gz"):
        # remove last 7 characters (".nii.gz")
        return basename[:-7]
    elif basename.endswith(".nii"):
        # remove last 4 characters (".nii")
        return basename[:-4]
    else:
        return basename

def process_scan_initial(bids_root, filepath, num_slices=10):
    # Grab just the filename (no directory)
    filename = os.path.basename(filepath)
    # Now remove .nii or .nii.gz, if present
    base_no_ext = strip_nii_gz(filename)
    
    logger.info(f"[Initial QC] Processing {filepath} ...")

    # 1) Load original data
    img = nib.load(filepath)
    data = img.get_fdata()
    
    # 2) Find slices of interest
    slice_indices = find_slices_of_interest(data, num_slices=num_slices)

    # 3) Plot & save to results folder
    results_dir = ensure_results_dir(bids_root, filepath)
    original_png = os.path.join(results_dir, f"{base_no_ext}_original_slices.png")
    plot_slices(data, slice_indices, original_png, title=f"{base_no_ext} - Original", nrows=2, ncols=5)

    # 4) Stats & density
    intensity_stats = analyze_nifti(filepath)
    if intensity_stats:
        stats_csv_path = os.path.join(results_dir, f"{base_no_ext}_stats.csv")
        pd.DataFrame([intensity_stats]).to_csv(stats_csv_path, index=False)

        density_svg_path = os.path.join(results_dir, f"{base_no_ext}_density.svg")
        create_density_plot_and_save(
            data,
            density_svg_path,
            title=f"Density Plot - {base_no_ext}"
        )

    logger.info(f"[Initial QC] Finished processing {filepath}.\n")

def traverse_bids_initial(bids_root, scan_type="T1w", num_slices=10):
    """
    Only processes original data. 
    """
    logger.info(f"[Initial QC] Starting traversal of {bids_root} for scan type {scan_type}...")

    for root, dirs, files in os.walk(bids_root):
        if "results" in root:
            continue

        for fname in files:
            # Only proceed if it matches the scan type, e.g. T1w
            if (fname.endswith(".nii") or fname.endswith(".nii.gz")) and (scan_type in fname):
                fullpath = os.path.join(root, fname)
                process_scan_initial(bids_root, fullpath, num_slices=num_slices)

    logger.info("[Initial QC] Finished processing all files.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Initial QC pipeline (no skull stripping).")
    parser.add_argument("bids_root", help="Path to the BIDS root directory")
    parser.add_argument("scan_type", help="Scan type substring to match, e.g. T1w or T2w")
    parser.add_argument("--num_slices", type=int, default=10, 
                        help="Number of slices to display (default: 10)")
    args = parser.parse_args()

    traverse_bids_initial(args.bids_root, scan_type=args.scan_type, num_slices=args.num_slices)