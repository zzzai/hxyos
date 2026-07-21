import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement, StrictMode, type ReactNode } from "react";

import { useVoiceCapture } from "./useVoiceCapture";

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];

  readonly stream: MediaStream;
  readonly mimeType = "audio/webm";
  state: RecordingState = "inactive";
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(stream: MediaStream) {
    this.stream = stream;
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.ondataavailable?.({
      data: new Blob(["voice"], { type: "audio/webm" }),
    } as BlobEvent);
    this.onstop?.(new Event("stop"));
  }
}

function browserAudio() {
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
  const getUserMedia = vi.fn().mockResolvedValue(stream);
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  return { getUserMedia, stop, stream };
}

describe("useVoiceCapture", () => {
  beforeEach(() => {
    FakeMediaRecorder.instances = [];
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("reports unsupported browsers without requesting permission", async () => {
    vi.stubGlobal("navigator", {});
    vi.stubGlobal("MediaRecorder", undefined);
    const { result } = renderHook(() => useVoiceCapture({ onCaptured: vi.fn() }));

    expect(result.current.status).toBe("unsupported");
    await act(async () => result.current.start());

    expect(result.current.error).toBe("当前浏览器不支持录音，请改用文件上传");
  });

  it("shows a recoverable error when microphone permission is denied", async () => {
    const getUserMedia = vi.fn().mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    const { result } = renderHook(() => useVoiceCapture({ onCaptured: vi.fn() }));

    await act(async () => result.current.start());

    expect(result.current.status).toBe("error");
    expect(result.current.error).toBe("无法使用麦克风，请检查浏览器权限");
  });

  it("starts recording and exposes elapsed duration", async () => {
    vi.useFakeTimers();
    const { getUserMedia } = browserAudio();
    const { result } = renderHook(() => useVoiceCapture({ onCaptured: vi.fn() }));

    await act(async () => result.current.start());
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(result.current.status).toBe("recording");

    act(() => vi.advanceTimersByTime(2_100));
    expect(result.current.durationSeconds).toBe(2);
  });

  it("starts recording after the StrictMode effect lifecycle check", async () => {
    const { getUserMedia } = browserAudio();
    const { result } = renderHook(
      () => useVoiceCapture({ onCaptured: vi.fn() }),
      {
        wrapper: ({ children }: { children: ReactNode }) =>
          createElement(StrictMode, null, children),
      },
    );

    await act(async () => result.current.start());

    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(result.current.status).toBe("recording");
  });

  it("stops recording, releases the microphone, and returns an audio file", async () => {
    const onCaptured = vi.fn();
    const { stop } = browserAudio();
    const { result } = renderHook(() => useVoiceCapture({ onCaptured }));

    await act(async () => result.current.start());
    act(() => result.current.stop());

    await waitFor(() => expect(onCaptured).toHaveBeenCalledOnce());
    expect(onCaptured.mock.calls[0][0]).toBeInstanceOf(File);
    expect(onCaptured.mock.calls[0][0]).toMatchObject({ type: "audio/webm" });
    expect(stop).toHaveBeenCalledOnce();
    expect(result.current.status).toBe("idle");
  });

  it("cancels without returning audio and releases the microphone", async () => {
    const onCaptured = vi.fn();
    const { stop } = browserAudio();
    const { result } = renderHook(() => useVoiceCapture({ onCaptured }));

    await act(async () => result.current.start());
    act(() => result.current.cancel());

    expect(onCaptured).not.toHaveBeenCalled();
    expect(stop).toHaveBeenCalledOnce();
    expect(result.current.status).toBe("idle");
  });

  it("retries permission after an initial denial", async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    const getUserMedia = vi
      .fn()
      .mockRejectedValueOnce(new DOMException("Denied", "NotAllowedError"))
      .mockResolvedValueOnce(stream);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
    const { result } = renderHook(() => useVoiceCapture({ onCaptured: vi.fn() }));

    await act(async () => result.current.start());
    expect(result.current.status).toBe("error");

    await act(async () => result.current.retry());
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe("recording");
  });

  it("cleans up an active recording when the composer unmounts", async () => {
    const { stop } = browserAudio();
    const { result, unmount } = renderHook(() =>
      useVoiceCapture({ onCaptured: vi.fn() }),
    );

    await act(async () => result.current.start());
    unmount();

    expect(stop).toHaveBeenCalledOnce();
    expect(FakeMediaRecorder.instances[0].state).toBe("inactive");
  });
});
