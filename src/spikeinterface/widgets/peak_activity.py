from __future__ import annotations

import numpy as np


from .base import BaseWidget, to_attr


class PeakActivityMapWidget(BaseWidget):
    """
    Plots spike rate (estimated with detect_peaks()) as 2D activity map.

    Can be static (bin_duration_s=None) or animated (bin_duration_s=60.)

    Parameters
    ----------
    recording : RecordingExtractor
        The recording extractor object.
    peaks : None or numpy array
        Optionally can give already detected peaks
        to avoid multiple computation.
    detect_peaks_kwargs : None or dict, default: None
        If peaks is None here the kwargs for detect_peak function.
    bin_duration_s : None or float, default: None
        If None then static image
        If not None then it is an animation per bin.
    with_contact_color : bool, default: True
        Plot rates with contact colors
    with_interpolated_map : bool, default: True
        Plot rates with interpolated map
    with_channel_ids : bool, default: False
        Add channel ids text on the probe
    fixed_color_range : bool or tuple of length=2, default: False
        Fixes the color bar range when animating or plotting
        in case of a length 2 tuple [vmin,vmax], uses that to fixes the colorbar range
        in case of bool
            For Animation
                True implies fixed range for all frames
                False implies range changing based on min-max of each frame
            For Plotting
                True/False both use min-max of the entire time-series via imshow defaults
    """

    def __init__(
        self,
        recording,
        peaks,
        bin_duration_s=None,
        with_contact_color=True,
        with_interpolated_map=True,
        with_channel_ids=False,
        with_color_bar=True,
        fixed_color_range=True,
        backend=None,
        **backend_kwargs,
    ):
        data_plot = dict(
            recording=recording,
            peaks=peaks,
            bin_duration_s=bin_duration_s,
            with_contact_color=with_contact_color,
            with_interpolated_map=with_interpolated_map,
            with_channel_ids=with_channel_ids,
            with_color_bar=with_color_bar,
            fixed_color_range=fixed_color_range,
        )

        BaseWidget.__init__(self, data_plot, backend=backend, **backend_kwargs)

    def plot_matplotlib(self, data_plot, **backend_kwargs):
        import matplotlib.pyplot as plt
        from .utils_matplotlib import make_mpl_figure

        dp = to_attr(data_plot)
        self.figure, self.axes, self.ax = make_mpl_figure(**backend_kwargs)

        rec = dp.recording
        peaks = dp.peaks

        fs = rec.get_sampling_frequency()
        duration = rec.get_total_duration()

        probes = rec.get_probes()
        assert len(probes) == 1, (
            "Activity map is only available for a single probe. If you have a probe group, "
            "consider splitting the recording from different probes"
        )
        probe = probes[0]

        if dp.bin_duration_s is None:
            if type(dp.fixed_color_range) in [tuple, list]:
                self.vmin, self.vmax = dp.fixed_color_range
                self._plot_one_bin(
                    rec,
                    probe,
                    peaks,
                    duration,
                    dp.with_channel_ids,
                    dp.with_contact_color,
                    dp.with_interpolated_map,
                    dp.with_color_bar,
                    vmin=self.vmin,
                    vmax=self.vmax,
                )
            else:
                self._plot_one_bin(
                    rec,
                    probe,
                    peaks,
                    duration,
                    dp.with_channel_ids,
                    dp.with_contact_color,
                    dp.with_interpolated_map,
                    dp.with_color_bar,
                )
        else:
            bin_size = int(dp.bin_duration_s * fs)
            num_frames = int(duration / dp.bin_duration_s)

            # Compute max values across all time bins if needed
            if type(dp.fixed_color_range) == bool and dp.fixed_color_range == True:
                all_rates = []
                for i in range(num_frames):
                    i0, i1 = np.searchsorted(peaks["sample_index"], [bin_size * i, bin_size * (i + 1)])
                    local_peaks = peaks[i0:i1]
                    rates = self._compute_rates(rec, local_peaks, dp.bin_duration_s)
                    all_rates.append(rates)
                all_rates = np.concatenate(all_rates)
                self.vmin, self.vmax = np.min(all_rates), np.max(all_rates)
            if type(dp.fixed_color_range) in [tuple, list]:
                self.vmin, self.vmax = dp.fixed_color_range
            else:
                self.vmin, self.vmax = None, None

            # Create a colorbar once
            dummy_image = self.ax.imshow([[0, 1]], visible=False, aspect="auto")
            self.cbar = self.figure.colorbar(dummy_image, ax=self.ax, label="Peaks (Hz)")

            # Create a text artist for displaying time
            self.time_text = self.ax.text(0.02, 0.98, "", transform=self.ax.transAxes, va="top", ha="left")

            def animate_func(i):
                self.ax.clear()
                i0, i1 = np.searchsorted(peaks["sample_index"], [bin_size * i, bin_size * (i + 1)])
                local_peaks = peaks[i0:i1]
                artists = self._plot_one_bin(
                    rec=rec,
                    probe=probe,
                    peaks=local_peaks,
                    duration=dp.bin_duration_s,
                    with_channel_ids=dp.with_channel_ids,
                    with_contact_color=dp.with_contact_color,
                    with_interpolated_map=dp.with_interpolated_map,
                    with_color_bar=False,
                    vmin=self.vmin,
                    vmax=self.vmax,
                )

                # Update colorbar
                if artists and isinstance(artists[-1], plt.matplotlib.image.AxesImage):
                    self.cbar.update_normal(artists[-1])

                # Update time text
                current_time = i * dp.bin_duration_s
                self.time_text.set_text(f"Time: {current_time:.2f} s")
                self.ax.add_artist(self.time_text)

                artists += (self.time_text,)
                return artists

            from matplotlib.animation import FuncAnimation

            self.animation = FuncAnimation(self.figure, animate_func, frames=num_frames, interval=100, blit=False)

    def _compute_rates(self, rec, peaks, duration):
        rates = np.zeros(rec.get_num_channels(), dtype="float64")
        for chan_ind, chan_id in enumerate(rec.channel_ids):
            mask = peaks["channel_index"] == chan_ind
            num_spike = np.sum(mask)
            rates[chan_ind] = num_spike / duration
        return rates

    def _plot_one_bin(
        self,
        rec,
        probe,
        peaks,
        duration,
        with_channel_ids,
        with_contact_color,
        with_interpolated_map,
        with_color_bar,
        vmin=None,
        vmax=None,
    ):
        rates = self._compute_rates(rec, peaks, duration)

        self.artists = ()
        if with_contact_color:
            text_on_contact = None
            if with_channel_ids:
                text_on_contact = rec.channel_ids

            from probeinterface.plotting import plot_probe

            poly, poly_contour = plot_probe(
                probe,
                ax=self.ax,
                contacts_values=rates,
                probe_shape_kwargs={"facecolor": "w", "alpha": 0.1},
                contacts_kargs={"alpha": 1.0},
                text_on_contact=text_on_contact,
            )
            if vmin is not None and vmax is not None:
                poly.set_clim(self.vmin, self.vmax)
            self.artists = self.artists + (poly, poly_contour)

        if with_interpolated_map:
            image, xlims, ylims = probe.to_image(
                rates, pixel_size=0.5, num_pixel=None, method="linear", xlims=None, ylims=None
            )
            im = self.ax.imshow(image, extent=xlims + ylims, origin="lower", alpha=0.5, vmin=vmin, vmax=vmax)
            self.artists = self.artists + (im,)

        if with_color_bar:
            self.cbar = self.figure.colorbar(im, ax=self.ax, label=f"Peak rate (Hz)")

        return self.artists
