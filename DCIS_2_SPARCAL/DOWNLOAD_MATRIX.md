# Getting `snv_matrix.pkl`

The SNV presence matrix (`snv_matrix.pkl`, ~235 MB) is too large for the git
repo, so it is published as a **GitHub Release asset** instead.

Download it into **this folder** (next to `DCIS_2_SPARCAL.config`):

```bash
cd DCIS_2_SPARCAL
curl -L -o snv_matrix.pkl \
  https://github.com/CyclopsRay/SpatialOmicViewer/releases/download/DCIS_2_SPARCAL-v1/snv_matrix.pkl
```

(or grab it from the repo's **Releases** page in a browser).

The config expects it at `snv_matrix.pkl`; once it's here the study opens
normally. Format: pandas-pickled uint8 DataFrame, rows = spot barcodes
(`AAAC…-1`), cols = `{chrom}_{pos}_{ref}_{alt}` (no `chr`), value = presence.
