import numpy as np
import soundfile as sf

from setbuilder.audio import TARGET_SR, load_audio_16k_mono


def test_load_synthetic_wav(tmp_path):
    sr, secs = 44100, 2.0
    t = np.arange(int(sr * secs)) / sr
    stereo = np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 220 * t)], axis=1)
    path = tmp_path / "tone.wav"
    sf.write(path, stereo.astype(np.float32), sr)

    audio = load_audio_16k_mono(str(path))

    assert audio is not None
    assert audio.ndim == 1
    assert audio.dtype == np.float32
    assert abs(len(audio) - int(TARGET_SR * secs)) <= 2
    assert np.isfinite(audio).all()


def test_load_missing_returns_none(tmp_path):
    assert load_audio_16k_mono(str(tmp_path / "nope.wav")) is None
