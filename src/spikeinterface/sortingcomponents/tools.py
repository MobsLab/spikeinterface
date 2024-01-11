import numpy as np
import psutil

from spikeinterface.core.node_pipeline import run_node_pipeline, ExtractSparseWaveforms, PeakRetriever
from spikeinterface.core.waveform_tools import extract_waveforms_to_single_buffer
from spikeinterface.core.job_tools import split_job_kwargs


def make_multi_method_doc(methods, ident="    "):
    doc = ""

    doc += "method: " + ", ".join(f"'{method.name}'" for method in methods) + "\n"
    doc += ident + "    Method to use.\n"

    for method in methods:
        doc += "\n"
        doc += ident + f"arguments for method='{method.name}'"
        for line in method.params_doc.splitlines():
            doc += ident + line + "\n"

    return doc


def extract_waveform_at_max_channel(rec, peaks, ms_before=0.5, ms_after=1.5, **job_kwargs):
    """
    Helper function to extract waveforms at the max channel from a peak list


    """
    n = rec.get_num_channels()
    unit_ids = np.arange(n, dtype="int64")
    sparsity_mask = np.eye(n, dtype="bool")

    spikes = np.zeros(
        peaks.size, dtype=[("sample_index", "int64"), ("unit_index", "int64"), ("segment_index", "int64")]
    )
    spikes["sample_index"] = peaks["sample_index"]
    spikes["unit_index"] = peaks["channel_index"]
    spikes["segment_index"] = peaks["segment_index"]

    nbefore = int(ms_before * rec.sampling_frequency / 1000.0)
    nafter = int(ms_after * rec.sampling_frequency / 1000.0)

    all_wfs = extract_waveforms_to_single_buffer(
        rec,
        spikes,
        unit_ids,
        nbefore,
        nafter,
        mode="shared_memory",
        return_scaled=False,
        sparsity_mask=sparsity_mask,
        copy=True,
        **job_kwargs,
    )

    return all_wfs


def get_prototype_spike(recording, peaks, job_kwargs, nb_peaks=1000, ms_before=0.5, ms_after=0.5):
    if peaks.size > nb_peaks:
        idx = np.sort(np.random.choice(len(peaks), nb_peaks, replace=False))
        some_peaks = peaks[idx]
    else:
        some_peaks = peaks

    nbefore = int(ms_before * recording.sampling_frequency / 1000.0)

    waveforms = extract_waveform_at_max_channel(
        recording, some_peaks, ms_before=ms_before, ms_after=ms_after, **job_kwargs
    )
    prototype = np.median(waveforms[:, :, 0] / (waveforms[:, nbefore, 0][:, np.newaxis]), axis=0)
    return prototype


def cache_preprocessing(recording, mode="memory", max_ram_limit=0.5, keep_cache_afterwards=False, **extra_kwargs):
    assert mode in ["memory", "zarr", "folder"]
    save_kwargs, job_kwargs = split_job_kwargs(extra_kwargs)

    if mode == "memory":
        assert 0 < max_ram_limit < 1
        memory_usage = max_ram_limit * psutil.virtual_memory()[4]
        if recording.get_total_memory_size() < memory_usage:
            recording = recording.save_to_memory(format="memory", shared=True, **job_kwargs)
        else:
            print("Recording too large to be preloaded in RAM...")
    elif mode == "folder":
        recording = recording.save_to_folder(**extra_kwargs)
    elif mode == "zarr":
        recording = recording.save_to_zarr(**extra_kwargs)

    return recording


def clean_preprocessing(recording, mode="memory", keep_cache_afterwards=False, **extra_kwargs):
    assert mode in ["memory", "zarr", "folder"]

    if mode == "memory":
        del recording
    elif mode in ["folder", "zarr"]:
        if not keep_cache_afterwards:
            import shutil

            shutil.rmtree(recording._kwargs["folder_path"])
    return
