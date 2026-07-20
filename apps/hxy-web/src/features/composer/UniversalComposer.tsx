import {
  ArrowUp,
  FileText,
  Paperclip,
  X,
} from "lucide-react";
import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
} from "react";

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
  const canSubmit = !disabled && !pending && Boolean(value.trim() || selectedFile);
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
        {canAttach ? (
          <label className="attachment-control" title="添加资料">
            <span className="visually-hidden">添加资料</span>
            <Paperclip aria-hidden="true" />
            <input
              type="file"
              aria-label="添加资料"
              disabled={disabled || pending}
              onChange={chooseFile}
            />
          </label>
        ) : (
          <span aria-hidden="true" />
        )}
        <span className="composer-hint">直接说或上传，系统会自动处理</span>
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
