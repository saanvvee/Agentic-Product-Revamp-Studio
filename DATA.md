# Datasets: sources, licences, citations

**No dataset files are committed to this repository.** `data/` and `datasets/`
are in `.gitignore` from the first commit. This repository is public and MVTec
AD is a NonCommercial licence, so committing it would be a licence violation as
well as a repository-size problem.

Everything here is used for **non-commercial academic research** as part of
CSE3101 Agentic AI coursework at BML Munjal University.

## What we use

| Dataset | Modality | Licence | Gate |
|---|---|---|---|
| MIMII (public 1.0) | Audio | **CC BY-SA 4.0** | Open download |
| MVTec AD | Vision | **CC BY-NC-SA 4.0** | Registration form |
| AI4I 2020 | Telemetry | **CC BY 4.0** | Open, via `ucimlrepo` |

### Licence note on MIMII

The original MIMII 1.0 release is Attribution-**ShareAlike**, *not*
NonCommercial. The MIMII DG and MIMII DUE variants are CC BY-NC-SA. We use the
original, and the distinction is worth stating because it is commonly
misreported.

## Download scope

We deliberately take a subset. The full pull is tens of gigabytes and buys no
additional orchestration result (PRD S7.3, cut in v1.1).

| Dataset | What we take | Approx size |
|---|---|---|
| MIMII | +6 dB SNR, **fan only**, all four model IDs (00, 02, 04, 06) | ~2.5 GB |
| MVTec AD | **`metal_nut` and `screw` only** | ~1 GB |
| AI4I 2020 | Everything | 500 KB |

The four MIMII model IDs are what give us three distinct machines from one
machine type: model ID becomes machine identity, so per-machine history in the
memory store is real rather than invented.

## How to get them

```bash
bash scripts/download_data.sh
```

MVTec AD can also be fetched automatically by anomalib's data module, which
downloads to `./datasets/` by default. **Note that path**: it is not `./data/`,
and it is separately gitignored for exactly that reason.

### If the official MVTec URL fails

Two fallbacks, in order of preference:

1. **`MSherbinii/mvtec-ad-metal-nut`** on Hugging Face — preserves the original
   MVTec directory layout (`metal_nut/train/good/…`, `metal_nut/ground_truth/…`)
   that anomalib expects, at ~166 MB for one category.
2. `Voxel51/mvtec-ad` — **not a drop-in replacement.** It is stored in flat
   FiftyOne format (`data/data_0/000.png`), so anomalib's `MVTecAD` datamodule
   cannot read it without a conversion script. PRD S7.1 lists this as the R4/R5
   fallback; that entry now carries this caveat.

Verify file counts against the official release before trusting any third-party
re-upload for reported results.

## A limitation we declare openly

No public dataset provides time-aligned multi-modal recordings of the same
industrial asset. We construct a **synthetic facility** that composes these three
real public datasets into synchronised incident events.

> Detector inputs are real. The cross-modal alignment is synthetic. Ambiguity
> levels are constructed in calibrated detector-score space, not in physics.

This is stated in the report rather than hidden. An examiner who spots an
undeclared simulation will penalise it; a declared one is a point of rigour.

## Citations

```bibtex
@inproceedings{purohit2019mimii,
  title     = {{MIMII} Dataset: Sound Dataset for Malfunctioning Industrial
               Machine Investigation and Inspection},
  author    = {Purohit, Harsh and Tanabe, Ryo and Ichige, Kenji and Endo, Takashi
               and Nikaido, Yuki and Suefusa, Kaori and Kawaguchi, Yohei},
  booktitle = {Proc. 4th Workshop on Detection and Classification of Acoustic
               Scenes and Events (DCASE)},
  year      = {2019},
  note      = {arXiv:1909.09347}
}

@article{bergmann2021mvtec,
  title   = {The {MVTec} Anomaly Detection Dataset: A Comprehensive Real-World
             Dataset for Unsupervised Anomaly Detection},
  author  = {Bergmann, Paul and Batzner, Kilian and Fauser, Michael and
             Sattlegger, David and Steger, Carsten},
  journal = {International Journal of Computer Vision},
  volume  = {129},
  pages   = {1038--1059},
  year    = {2021}
}

@misc{matzka2020ai4i,
  title     = {{AI4I} 2020 Predictive Maintenance Dataset},
  author    = {Matzka, Stephan},
  year      = {2020},
  publisher = {UCI Machine Learning Repository},
  doi       = {10.24432/C5HS5C}
}
```

## Source URLs

- MIMII: https://zenodo.org/records/3384388
- MVTec AD: https://www.mvtec.com/company/research/datasets/mvtec-ad
- MVTec AD (HF, original layout, per-category): https://huggingface.co/datasets/MSherbinii/mvtec-ad-metal-nut
- MVTec AD (HF, FiftyOne format): https://huggingface.co/datasets/Voxel51/mvtec-ad
- AI4I 2020: https://archive.ics.uci.edu/dataset/601
