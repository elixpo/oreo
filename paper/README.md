# RV565 paper source

This directory contains the RV565 paper by Ayushman Bhattacharya (Pollinations
AI) and Anwesha Chakraborty (Department of Computer Science and Engineering,
JIS University). Contact: `ayushman.elixpo@gmail.com`. Target: arXiv cs.AR,
cross-listed to cs.MM.

Every number in the paper comes from a committed measurement or from a script
run over one. Do not add estimates. Projections are labelled as projections in
the text.

| Source | Produces |
| --- | --- |
| `measurements/video-benchmark-native-dma-stripes-aggregate-*.json` | Table 3 standalone row, Table 6, Section 6.2 |
| `measurements/video-benchmark-oreoos-gallery-*.json` | Table 3 integrated row |
| `../tools/analyze_rv565_paper.py` | Sections 6.3–6.6, Tables 4 and 5, Figure 4 |
| `figures/*.pdf` (from `schematics/build.sh`) | Figure 3 |

Run the derived analyses from the repository root. The label selects the
standalone aggregate; its media digest selects the matching Gallery record.
The script needs the evaluated container
(`experiments/video_dma/main/video.rv565`) and refuses any file whose SHA-256
differs from the measured one.

```bash
python3 -I tools/analyze_rv565_paper.py --label bbb-native-dma-stripes
```

## Evaluated revisions

The collectors hash the sources used for each run. The matching commits are:

| Path | Commit | Evidence |
| --- | --- | --- |
| Standalone `experiments/video_dma/main/main.c`, `sdkconfig.defaults` | `411f8f2` | `benchmark_source` and `sdkconfig_defaults` digests in each run JSON |
| `apps/gallery/src/app.py`, `oreoOS/launcher.py` | `dcca17b` | `gallery` and `launcher` digests in the Gallery JSON |
| `firmware/usermods/oreo_rv565/modoreo_rv565.c` | `de149c4` | `firmware_module` digest |
| Media `video.rv565` | not redistributed | SHA-256 `2bc5ea5b…3d9ce6` |

## Build

```bash
cd paper
latexmk -pdf rv565.tex
```

## Submit

1. Archive the repository on Zenodo and set `\artifactdoi` in `rv565.tex`
   and `doi` in `../CITATION.cff`.
2. Run `./make_arxiv.sh`. It refuses to package while the DOI is a
   placeholder or the build has warnings, then verifies that the staged
   sources compile without BibTeX.
3. Upload `rv565-arxiv.tar.gz` to arXiv: primary cs.AR, cross-list cs.MM,
   licence CC BY 4.0.
