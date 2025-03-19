# BIDS Quality Control Package (bids-qc-pkg)

A quality control tool for neuroimaging data in BIDS format. This package provides tools for structural and functional MRI quality control assessment and report generation.

## Installation

You can install the package directly from GitHub:

```bash
pip install git+https://github.com/InfantBrainAI/bids-qc-pkg.git
```

Or install in development mode for contributing:

```bash
git clone https://github.com/InfantBrainAI/bids-qc-pkg.git
cd bids-qc-pkg
pip install -e .
```

## Available Commands

After installation, the following commands will be available in your terminal:

### Structural MRI QC Commands

- `bids-qc-initial-struct` - Generate slice images for structural MRI data for manual review
- `bids-qc-annotate-struct` - Launch annotation server for reviewing and rating structural MRI data
- `bids-qc-final-struct` - Run processing pipeline (n4 bias correction, skull stripping) on selected structural MRI data

### Functional MRI QC Commands

- `bids-qc-fmri-qc` - Run QC on functional MRI data

## Usage Examples

Each command accepts a BIDS directory as input. Here are basic examples for each command:

### Initial Structural QC

```bash
bids-qc-initial-struct /path/to/bids/dataset [--options]
```

### Annotate Structural Images

```bash
bids-qc-annotate-struct /path/to/bids/dataset [--options]
```

This command launches a server environment on port 8080 that allows for manual annotation. Annotation results are saved in a CSV file.

### Final Structural Processing

```bash
bids-qc-final-struct /path/to/bids/dataset [--options]
```

Note: This command does not automatically read the CSV from annotation. You'll need to either:
- Remove scans you don't want to process, or
- Create a new directory with only the scans you've selected

### Review Skull-Stripped Images

```bash
bids-qc-annotate-struct /path/to/bids/dataset --final [--options]
```

Use this to review the skull-stripped images and check the quality of the skull stripping.

### Generate Structural Reports

```bash
bids-qc-report-struct /path/to/bids/dataset [--options]
```

### fMRI Quality Control

```bash
bids-qc-fmri-qc /path/to/bids/dataset [--options]
```

## Typical Workflow

1. **Generate slice images for review:**
   ```bash
   bids-qc-initial-struct /path/to/bids/dataset
   ```

2. **Launch annotation server and review images:**
   ```bash
   bids-qc-annotate-struct /path/to/bids/dataset
   ```
   - Access the server at http://localhost:8080
   - Review and rate each scan
   - Annotations are saved to a CSV file

3. **Process selected scans:**
   - Option 1: Remove unwanted scans from the dataset
   - Option 2: Create a new directory with only the scans you want to process
   ```bash
   bids-qc-final-struct /path/to/bids/dataset
   ```
   This step performs n4 bias correction and skull stripping on the selected scans.

4. **Review skull-stripped images:**
   ```bash
   bids-qc-annotate-struct /path/to/bids/dataset --final
   ```
   This allows you to check if the skull stripping was done properly.

## Output

Results are stored in the `results` directory within your BIDS dataset.

