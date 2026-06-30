---
name: hdf5-format
description: The CENTER-TBI HDF5 archival format and how manuEdge segments map to it
type: reference
---

# HDF5 archival format (the spine)

manuBeat archives bedside data into the HDF5 format from Cabeleira et al., *HDF5 based
data format for archiving complex neuro-monitoring data in TBI patients* (CENTER-TBI).
manuEdge's wire records are designed to drop straight into this structure. The paper PDF
lives in manuBeat at `pwa/public/HDF5 based data format...pdf`.

## File layout
```
<patient>_<date>.h5            root attrs: key metadata
├── numerics/      ≤1 Hz, 1-D float32, per modality (etco2, spo2, pbto2, hr, temperature)
├── waves/         waveforms, 1-D float32, per modality (abp, icp, ecg, cvp)
│   └── EEG/ ECoG/ composite: one dataset per channel (EEG.O1 …)
├── summaries/     composite [Excel-ts, 1xN float32]; minute + hour (server-derived)
├── episodic/      composite [Code, ts_ms, Duration, Comment, Value]
├── annotations/   composite [Code, ts_ms, Duration, Comment]
├── definitions/   eventTypes, indexStruct, qualityRef, qualityStruct (self-describing)
├── patient.info   dataset: [Field, Value] demographics (server/registry)
└── presentation   dataset: [Field, Value] non-identifying clinical (server/registry)
```
Per timeseries dataset attributes: **Index Table** `[start_index i64, start_time_us i64,
duration i64, sampling_hz f64]`, **Quality Table** `[ts_ms u64, code u32]` (bitset valid
until next entry), plus Units/Metric/Location/Modality/Source. Compression: ScaleOffset
for time series, GZip-6 for summaries.

## The mapping (segment = Index Table row)
- **TimeseriesSegment** → `numerics/<modality>` or `waves/<modality>` (`waves/EEG/<channel>`
  for composite). The segment's `start_time_us` + `sampling_hz` + `duration` ARE one Index
  Table row; its quality transitions become Quality Table rows.
- **Event** → `episodic/` or `annotations/`.
- `summaries/` is server-computed (Python). `patient.info`/`presentation`/`definitions`
  are server/static. **The Pi never emits these.**

A gap at the edge (dropout/interruption) ends a segment and starts a new one — exactly an
Index Table boundary. This is why store-and-forward and the archival format are the same
shape. Keep them aligned.

Time bases: Index Table start_time = µs since 1/1/1970; quality/episodic/annotation = ms
since 1/1/1970; summaries = Excel days since 1/1/1990.
