"""Gera um vídeo de teste e valida o NativeVideoPlayer."""

import os
import sys
import tempfile
import time

from fractions import Fraction

import numpy as np
import av

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from native_video_player import NativeVideoPlayer


def make_test_video(path, seconds=3.0, with_audio=True, with_video=True):
    container = av.open(path, "w")
    vstream = None
    astream = None

    if with_video:
        vstream = container.add_stream("libx264", rate=30)
        vstream.width = 320
        vstream.height = 180
        vstream.pix_fmt = "yuv420p"
        vstream.options = {"crf": "28", "preset": "ultrafast", "g": "15"}

    if with_audio:
        astream = container.add_stream("aac", rate=44100)
        astream.layout = "stereo"

    if with_video:
        total = int(seconds * 30)
        for i in range(total):
            arr = np.full((180, 320, 3), 20, dtype=np.uint8)
            x = int((i / max(1, total - 1)) * 240)
            arr[40:140, x : x + 80] = (255, 180, 0)
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            frame.pts = i
            frame.time_base = Fraction(1, 30)
            for packet in vstream.encode(frame):
                container.mux(packet)
        for packet in vstream.encode(None):
            container.mux(packet)

    if with_audio:
        sr = 44100
        n = int(seconds * sr)
        t = np.arange(n, dtype=np.float32) / sr
        mono = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        stereo = np.stack([mono, mono], axis=1)

        block = 1024
        offset = 0
        pts_samples = 0
        while offset < n:
            chunk = stereo[offset : offset + block]
            if len(chunk) < block:
                pad = np.zeros((block - len(chunk), 2), dtype=np.float32)
                chunk = np.concatenate([chunk, pad], axis=0)
            af = av.AudioFrame.from_ndarray(
                np.ascontiguousarray(chunk.T), format="fltp", layout="stereo"
            )
            af.sample_rate = sr
            af.pts = pts_samples
            af.time_base = Fraction(1, sr)
            for packet in astream.encode(af):
                container.mux(packet)
            offset += block
            pts_samples += block
        for packet in astream.encode(None):
            container.mux(packet)

    container.close()
    return path


def wait_until(predicate, timeout=5.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return False


def test_full(path):
    player = NativeVideoPlayer()
    player.set_volume(10)
    player.load(path)

    duration = player.get_duration()
    assert abs(duration - 3.0) < 0.3, f"duration invalida: {duration}"
    print(f"[ok] duration={duration:.3f}s")

    player.play()
    assert player.is_playing(), "deveria estar tocando"

    frames = 0
    saw_progress = False
    start = time.time()
    while time.time() - start < 1.6:
        img = player.get_ready_frame()
        if img is not None:
            frames += 1
            assert img.size == (320, 180), f"tamanho frame: {img.size}"
        if player.get_position() > 0.2:
            saw_progress = True
        time.sleep(0.01)

    assert frames > 5, f"poucos frames: {frames}"
    assert saw_progress, f"posicao nao avancou: {player.get_position()}"
    print(f"[ok] frames={frames} pos={player.get_position():.3f}")

    player.pause()
    assert player.is_paused(), "deveria pausar"
    pos_pause = player.get_position()
    time.sleep(0.4)
    pos_after = player.get_position()
    assert abs(pos_after - pos_pause) < 0.15, (
        f"posicao mudou na pausa: {pos_pause} -> {pos_after}"
    )
    print(f"[ok] pausa em {pos_after:.3f}s")

    player.seek_fraction(0.15)
    target = duration * 0.15
    ok = wait_until(lambda: abs(player.get_position() - target) < 0.08, 3.0)
    assert ok, f"seek falhou, pos={player.get_position()} esperado={target}"
    assert player._seek_target is None, "seek nao foi aplicado"
    print(f"[ok] seek pausado -> {player.get_position():.3f}s")

    player.resume()
    assert player.is_playing(), "deveria resumir"

    player.seek_fraction(0.9)
    finished = wait_until(
        lambda: (player.get_ready_frame() or True) and player.is_finished(),
        timeout=5.0,
        step=0.05,
    )
    assert finished, "nao terminou"
    assert not player.is_playing()
    print("[ok] finished no fim do video")

    player.stop()
    assert not player.is_loaded()
    print("[ok] stop")


def test_video_only(path):
    player = NativeVideoPlayer()
    player.load(path)
    player.play()
    time.sleep(0.5)
    assert player.get_position() > 0.2, player.get_position()
    frames = 0
    for _ in range(30):
        if player.get_ready_frame() is not None:
            frames += 1
        time.sleep(0.02)
    assert frames > 0, "sem frames (video only)"
    player.stop()
    print(f"[ok] video-only frames={frames}")


def main():
    tmp = tempfile.mkdtemp(prefix="ssctest_")
    p1 = os.path.join(tmp, "av.mp4")
    p2 = os.path.join(tmp, "v.mp4")

    print("Gerando videos de teste...")
    make_test_video(p1, seconds=3.0, with_audio=True, with_video=True)
    make_test_video(p2, seconds=2.0, with_audio=False, with_video=True)

    print("\nTeste: video + audio")
    test_full(p1)

    print("\nTeste: somente video")
    test_video_only(p2)

    print("\nTODOS OS TESTES PASSARAM")


if __name__ == "__main__":
    main()
