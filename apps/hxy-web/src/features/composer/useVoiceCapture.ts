import { useCallback, useEffect, useRef, useState } from "react";

export type VoiceCaptureStatus =
  | "unsupported"
  | "idle"
  | "requesting"
  | "recording"
  | "error";

interface UseVoiceCaptureOptions {
  onCaptured: (file: File) => void;
  maxDurationSeconds?: number;
}

interface VoiceCapture {
  status: VoiceCaptureStatus;
  durationSeconds: number;
  error: string | null;
  start: () => Promise<void>;
  stop: () => void;
  cancel: () => void;
  retry: () => Promise<void>;
}

const UNSUPPORTED_MESSAGE = "当前浏览器不支持录音，请改用文件上传";
const PERMISSION_MESSAGE = "无法使用麦克风，请检查浏览器权限";
const CAPTURE_MESSAGE = "录音没有保存，请重试";

function browserSupportsRecording() {
  return (
    typeof MediaRecorder !== "undefined" &&
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function"
  );
}

function recorderOptions(): MediaRecorderOptions | undefined {
  if (typeof MediaRecorder.isTypeSupported !== "function") return undefined;
  const mimeType = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
  ].find((candidate) => MediaRecorder.isTypeSupported(candidate));
  return mimeType ? { mimeType } : undefined;
}

function audioExtension(mimeType: string) {
  if (mimeType.includes("mp4")) return "m4a";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

export function useVoiceCapture({
  onCaptured,
  maxDurationSeconds = 120,
}: UseVoiceCaptureOptions): VoiceCapture {
  const supported = browserSupportsRecording();
  const [status, setStatus] = useState<VoiceCaptureStatus>(
    supported ? "idle" : "unsupported",
  );
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [error, setError] = useState<string | null>(
    supported ? null : UNSUPPORTED_MESSAGE,
  );
  const mountedRef = useRef(true);
  const requestRef = useRef(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const canceledRef = useRef(false);
  const stopRequestedRef = useRef(false);
  const startedAtRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCapturedRef = useRef(onCaptured);

  useEffect(() => {
    onCapturedRef.current = onCaptured;
  }, [onCaptured]);

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const finishWithError = useCallback(
    (message: string) => {
      stopTimer();
      releaseStream();
      recorderRef.current = null;
      if (!mountedRef.current) return;
      setStatus("error");
      setError(message);
    },
    [releaseStream, stopTimer],
  );

  const stop = useCallback(() => {
    stopRequestedRef.current = true;
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      try {
        recorder.stop();
      } catch {
        finishWithError(CAPTURE_MESSAGE);
      }
    }
  }, [finishWithError]);

  const start = useCallback(async () => {
    if (!browserSupportsRecording()) {
      setStatus("unsupported");
      setError(UNSUPPORTED_MESSAGE);
      return;
    }

    const request = ++requestRef.current;
    canceledRef.current = false;
    stopRequestedRef.current = false;
    chunksRef.current = [];
    setDurationSeconds(0);
    setError(null);
    setStatus("requesting");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current || request !== requestRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      streamRef.current = stream;
      const options = recorderOptions();
      const recorder = options
        ? new MediaRecorder(stream, options)
        : new MediaRecorder(stream);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => finishWithError(CAPTURE_MESSAGE);
      recorder.onstop = () => {
        stopTimer();
        releaseStream();
        recorderRef.current = null;
        stopRequestedRef.current = false;
        if (!mountedRef.current) return;
        if (canceledRef.current) {
          canceledRef.current = false;
          chunksRef.current = [];
          setDurationSeconds(0);
          setStatus("idle");
          return;
        }

        const mimeType = recorder.mimeType || chunksRef.current[0]?.type || "audio/webm";
        const audio = new Blob(chunksRef.current, { type: mimeType });
        chunksRef.current = [];
        if (audio.size === 0) {
          setStatus("error");
          setError(CAPTURE_MESSAGE);
          return;
        }
        const timestamp = new Date().toISOString().replaceAll(":", "-");
        onCapturedRef.current(
          new File([audio], `voice-${timestamp}.${audioExtension(mimeType)}`, {
            type: mimeType,
            lastModified: Date.now(),
          }),
        );
        setDurationSeconds(0);
        setStatus("idle");
      };

      recorder.start();
      startedAtRef.current = Date.now();
      setStatus("recording");
      timerRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAtRef.current) / 1_000);
        setDurationSeconds(elapsed);
        if (elapsed >= maxDurationSeconds) stop();
      }, 250);
      if (stopRequestedRef.current) stop();
    } catch {
      if (!mountedRef.current || request !== requestRef.current) return;
      finishWithError(PERMISSION_MESSAGE);
    }
  }, [finishWithError, maxDurationSeconds, releaseStream, stop, stopTimer]);

  const cancel = useCallback(() => {
    requestRef.current += 1;
    canceledRef.current = true;
    stopRequestedRef.current = false;
    stopTimer();
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.stop();
      return;
    }
    recorderRef.current = null;
    releaseStream();
    chunksRef.current = [];
    if (!mountedRef.current) return;
    setDurationSeconds(0);
    setError(null);
    setStatus("idle");
  }, [releaseStream, stopTimer]);

  useEffect(
    () => () => {
      mountedRef.current = false;
      requestRef.current += 1;
      canceledRef.current = true;
      stopTimer();
      const recorder = recorderRef.current;
      if (recorder?.state === "recording") recorder.stop();
      recorderRef.current = null;
      releaseStream();
    },
    [releaseStream, stopTimer],
  );

  return {
    status,
    durationSeconds,
    error,
    start,
    stop,
    cancel,
    retry: start,
  };
}
