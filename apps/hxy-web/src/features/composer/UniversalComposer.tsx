import {
  ArrowUp,
  FileText,
  Mic,
  Paperclip,
  Square,
  X,
} from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  useRef,
} from "react";
import { useVoiceCapture } from "./useVoiceCapture";

interface UniversalComposerProps {
  value: string;
  selectedFile: File | null;
  pending: boolean;
  disabled?: boolean;
  canAttach: boolean;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  onValueChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onSubmit: () => void;
}

export function UniversalComposer({
  value,
  selectedFile,
  pending,
  disabled = false,
  canAttach,
  inputRef,
  onValueChange,
  onFileChange,
  onSubmit,
}: UniversalComposerProps) {
  const voice = useVoiceCapture({ onCaptured: onFileChange });
  const touchRecordingRef = useRef(false);
  const suppressClickRef = useRef(false);
  const voiceBusy = voice.status === "requesting" || voice.status === "recording";
  const canSubmit =
    !disabled && !pending && !voiceBusy && Boolean(value.trim() || selectedFile);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canSubmit) onSubmit();
  };
  const submitOnEnter = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    if (canSubmit) onSubmit();
  };
  const chooseFile = (event: ChangeEvent<HTMLInputElement>) => {
    onFileChange(event.target.files?.[0] ?? null);
    event.target.value = "";
  };
  const beginVoice = () =>
    voice.status === "error" ? voice.retry() : voice.start();
  const holdToRecord = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerType !== "touch" && event.pointerType !== "pen") return;
    event.preventDefault();
    touchRecordingRef.current = true;
    suppressClickRef.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    void beginVoice();
  };
  const finishHold = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!touchRecordingRef.current) return;
    event.preventDefault();
    touchRecordingRef.current = false;
    voice.stop();
  };
  const cancelHold = () => {
    if (!touchRecordingRef.current) return;
    touchRecordingRef.current = false;
    voice.cancel();
  };

  return (
    <form className="universal-composer" data-testid="composer" onSubmit={submit}>
      <label className="visually-hidden" htmlFor="hxy-universal-composer">
        问问题，或记录刚刚发生的事
      </label>
      <textarea
        ref={inputRef}
        id="hxy-universal-composer"
        rows={2}
        maxLength={20_000}
        value={value}
        placeholder="问问题，或记录刚刚发生的事"
        disabled={disabled || pending}
        onChange={(event) => onValueChange(event.target.value)}
        onKeyDown={submitOnEnter}
      />

      {selectedFile ? (
        <div className="selected-file">
          <FileText aria-hidden="true" />
          <span>{selectedFile.name}</span>
          <button
            type="button"
            aria-label={`移除 ${selectedFile.name}`}
            disabled={pending}
            onClick={() => onFileChange(null)}
          >
            <X aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <div className="composer-actions">
        <div className="composer-tools">
          {canAttach ? (
            <label className="attachment-control" title="添加资料">
              <span className="visually-hidden">添加资料</span>
              <Paperclip aria-hidden="true" />
              <input
                type="file"
                aria-label="添加资料"
                disabled={disabled || pending || voiceBusy}
                onChange={chooseFile}
              />
            </label>
          ) : null}
          {canAttach && voice.status !== "unsupported" ? (
            <>
              <button
                className={`voice-control${
                  voice.status === "recording" ? " is-recording" : ""
                }`}
                type="button"
                aria-label={
                  voice.status === "recording"
                    ? "停止录音"
                    : voice.status === "requesting"
                      ? "正在请求麦克风"
                      : voice.status === "error"
                        ? "重试录音"
                        : "开始录音"
                }
                title={voice.status === "recording" ? "停止录音" : "开始录音"}
                disabled={
                  disabled ||
                  pending ||
                  (voice.status !== "recording" && Boolean(selectedFile))
                }
                onPointerDown={holdToRecord}
                onPointerUp={finishHold}
                onPointerCancel={cancelHold}
                onClick={() => {
                  if (suppressClickRef.current) {
                    suppressClickRef.current = false;
                    return;
                  }
                  if (voice.status === "requesting") return;
                  if (voice.status === "recording") voice.stop();
                  else void beginVoice();
                }}
              >
                {voice.status === "recording" ? (
                  <Square aria-hidden="true" />
                ) : (
                  <Mic aria-hidden="true" />
                )}
              </button>
              {voice.status === "recording" ? (
                <button
                  className="voice-control"
                  type="button"
                  aria-label="取消录音"
                  title="取消录音"
                  onClick={voice.cancel}
                >
                  <X aria-hidden="true" />
                </button>
              ) : null}
            </>
          ) : null}
        </div>
        <span
          className={`composer-hint${voice.status === "error" ? " is-error" : ""}`}
          role={voice.status === "error" ? "alert" : undefined}
        >
          {voice.status === "recording"
            ? `正在录音 ${formatDuration(voice.durationSeconds)}`
            : voice.status === "requesting"
              ? "正在连接麦克风"
              : voice.error ?? "直接说或上传，系统会自动处理"}
        </span>
        <button
          className="composer-submit"
          type="submit"
          aria-label="发送"
          disabled={!canSubmit}
        >
          <ArrowUp aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}

function formatDuration(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}
