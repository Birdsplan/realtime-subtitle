import numpy as np


def get_segment_cut_reason(
    audio_buffer,
    sample_rate,
    silence_threshold,
    silence_duration,
    max_phrase_duration,
    minimum_phrase_duration=2.0,
    soft_limit_duration=6.0,
    soft_silence_duration=0.4,
):
    """Return the reason to finalize an accumulated speech segment, or None."""
    if sample_rate <= 0:
        raise ValueError("sample_rate must be greater than zero")

    samples = np.asarray(audio_buffer, dtype=np.float32)
    buffer_duration = len(samples) / sample_rate
    if buffer_duration <= 0.5:
        return None

    if (
        buffer_duration > minimum_phrase_duration
        and _tail_is_silent(
            samples,
            sample_rate,
            silence_duration,
            silence_threshold,
        )
    ):
        return "silence"

    if (
        buffer_duration > soft_limit_duration
        and _tail_is_silent(
            samples,
            sample_rate,
            soft_silence_duration,
            silence_threshold,
        )
    ):
        return "soft_limit"

    if buffer_duration > max_phrase_duration:
        return "hard_limit"

    return None


def _tail_is_silent(audio_buffer, sample_rate, duration, threshold):
    tail_samples = int(sample_rate * duration)
    if tail_samples <= 0 or len(audio_buffer) <= tail_samples:
        return False

    tail = audio_buffer[-tail_samples:]
    rms = float(np.sqrt(np.mean(tail**2)))
    return rms < threshold
