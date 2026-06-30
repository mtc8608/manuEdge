"""Modality registry — the shared contract for what each signal *is*.

A driver only declares "I produce ``abp``"; everything downstream (HDF5 group
placement, units, default rate, composite channels) is looked up here. This
registry is part of the wire contract and should stay in sync with manuBeat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import Group


@dataclass(frozen=True, slots=True)
class ModalitySpec:
    modality: str
    group: Group
    default_hz: float
    units: str
    metric: str = ""
    # For composite modalities (e.g. EEG), the channel names stored as a group of
    # datasets under waves/<modality>/<channel>.
    composite_channels: tuple[str, ...] = ()


# Seeded from Table 1 of the HDF5 paper. Extend as new devices come online.
REGISTRY: dict[str, ModalitySpec] = {
    # --- numerics (<= 1 Hz) ---
    "etco2": ModalitySpec("etco2", Group.NUMERICS, 1.0, "mmHg", "End-tidal CO2"),
    "spo2": ModalitySpec("spo2", Group.NUMERICS, 1.0, "%", "Oxygen saturation"),
    "pbto2": ModalitySpec("pbto2", Group.NUMERICS, 1.0, "mmHg", "Brain tissue O2"),
    "hr": ModalitySpec("hr", Group.NUMERICS, 1.0, "bpm", "Heart rate"),
    "temperature": ModalitySpec("temperature", Group.NUMERICS, 1.0, "degC", "Temperature"),
    # --- waveforms ---
    "abp": ModalitySpec("abp", Group.WAVES, 100.0, "mmHg", "Arterial blood pressure"),
    "icp": ModalitySpec("icp", Group.WAVES, 100.0, "mmHg", "Intracranial pressure"),
    "ecg": ModalitySpec("ecg", Group.WAVES, 250.0, "mV", "Electrocardiogram"),
    "cvp": ModalitySpec("cvp", Group.WAVES, 100.0, "mmHg", "Central venous pressure"),
    "eeg": ModalitySpec(
        "eeg", Group.WAVES, 256.0, "uV", "Electroencephalogram",
        composite_channels=("O1", "Oz", "Pz", "T5"),
    ),
    # --- bench sensors on the Waveshare AD HAT (for prototype wiring) ---
    "bench_pot": ModalitySpec("bench_pot", Group.WAVES, 50.0, "V", "Onboard potentiometer (AIN0)"),
    "bench_ldr": ModalitySpec("bench_ldr", Group.WAVES, 50.0, "V", "Onboard photoresistor (AIN1)"),
}


def get(modality: str) -> ModalitySpec:
    try:
        return REGISTRY[modality]
    except KeyError as exc:
        raise KeyError(
            f"unknown modality {modality!r}; add it to manuedge.modality.REGISTRY"
        ) from exc
