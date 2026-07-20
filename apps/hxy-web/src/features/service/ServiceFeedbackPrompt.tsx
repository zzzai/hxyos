import {
  CheckCircle2,
  Mic,
  RefreshCw,
  Send,
  Square,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import type { MaterialClient } from "../../api/materials";
import type { ServiceClient, ServiceContext } from "../../api/services";
import { useVoiceCapture } from "../composer/useVoiceCapture";

interface ServiceFeedbackPromptProps {
  serviceClient: ServiceClient;
  materialClient: MaterialClient;
  clientFeedbackIdFactory: () => string;
  uploadIdFactory: () => string;
  onActiveChange?: (active: boolean) => void;
}

type LoadStatus = "loading" | "ready" | "error";
type SubmitStatus = "idle" | "uploading" | "submitting" | "complete" | "error";

export function ServiceFeedbackPrompt({
  serviceClient,
  materialClient,
  clientFeedbackIdFactory,
  uploadIdFactory,
  onActiveChange,
}: ServiceFeedbackPromptProps) {
  const [context, setContext] = useState<ServiceContext | null>(null);
  const [text, setText] = useState("");
  const [voiceAssetId, setVoiceAssetId] = useState<string | null>(null);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [submitStatus, setSubmitStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setLoadStatus("loading");
    setMessage("");
    try {
      const response = await serviceClient.listRecent(10);
      const unfinished = response.contexts.find(
        (candidate) => candidate.status !== "closed" && candidate.feedback_count === 0,
      );
      onActiveChange?.(unfinished !== undefined);
      setContext(unfinished ?? null);
      setLoadStatus("ready");
    } catch {
      onActiveChange?.(true);
      setLoadStatus("error");
    }
  }, [onActiveChange, serviceClient]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(
    () => () => {
      onActiveChange?.(false);
    },
    [onActiveChange],
  );

  const uploadVoice = useCallback(
    async (file: File) => {
      setVoiceFile(file);
      setVoiceAssetId(null);
      setSubmitStatus("uploading");
      setMessage("");
      try {
        const response = await materialClient.uploadMaterial(
          file,
          "服务反馈录音",
          uploadIdFactory(),
        );
        setVoiceAssetId(response.material.id);
        setSubmitStatus("idle");
      } catch {
        setSubmitStatus("error");
        setMessage("录音没有上传成功");
      }
    },
    [materialClient, uploadIdFactory],
  );

  const voice = useVoiceCapture({ onCaptured: (file) => void uploadVoice(file) });

  const submit = async () => {
    const feedbackText = text.trim();
    if (
      !context ||
      (!feedbackText && !voiceAssetId) ||
      submitStatus === "uploading" ||
      submitStatus === "submitting"
    ) {
      return;
    }
    setSubmitStatus("submitting");
    setMessage("");
    try {
      await serviceClient.addFeedback(context.id, {
        clientFeedbackId: clientFeedbackIdFactory(),
        text: feedbackText,
        sourceAssetIds: voiceAssetId ? [voiceAssetId] : [],
      });
      setSubmitStatus("complete");
      setText("");
    } catch {
      setSubmitStatus("error");
      setMessage("服务反馈没有提交成功，请重试");
    }
  };

  if (loadStatus === "loading") return null;

  if (loadStatus === "error") {
    return (
      <section className="service-feedback-prompt is-error" aria-label="服务反馈">
        <p role="alert">最近服务暂时没有加载出来</p>
        <button type="button" aria-label="重新加载服务" onClick={() => void load()}>
          <RefreshCw aria-hidden="true" />
          重试
        </button>
      </section>
    );
  }

  if (!context) return null;

  if (submitStatus === "complete") {
    return (
      <section className="service-feedback-prompt is-complete" aria-label="服务反馈">
        <CheckCircle2 aria-hidden="true" />
        <div>
          <strong>服务反馈已记录</strong>
          <span>{context.customer_display}</span>
        </div>
      </section>
    );
  }

  const recording = voice.status === "recording";
  const busy = submitStatus === "uploading" || submitStatus === "submitting";
  const canSubmit = Boolean(text.trim() || voiceAssetId) && !busy;

  return (
    <section className="service-feedback-prompt" aria-labelledby="service-feedback-title">
      <header>
        <div>
          <span>刚刚的服务</span>
          <h2 id="service-feedback-title">{context.customer_display}</h2>
        </div>
        <strong>{context.service_label}</strong>
      </header>

      <label htmlFor={`service-feedback-${context.id}`}>服务反馈</label>
      <textarea
        id={`service-feedback-${context.id}`}
        rows={2}
        maxLength={4000}
        value={text}
        disabled={busy}
        placeholder="顾客感受、特殊情况或需要跟进的事"
        onChange={(event) => {
          setText(event.target.value);
          setMessage("");
        }}
      />

      <div className="service-feedback-actions">
        {voice.status !== "unsupported" ? (
          <button
            className={recording ? "is-recording" : undefined}
            type="button"
            aria-label={recording ? "结束录音" : "录音反馈"}
            title={recording ? "结束录音" : "录音反馈"}
            disabled={busy}
            onClick={() => (recording ? voice.stop() : void voice.start())}
          >
            {recording ? <Square aria-hidden="true" /> : <Mic aria-hidden="true" />}
            {recording ? `${voice.durationSeconds} 秒` : "录音"}
          </button>
        ) : null}
        <span className="service-feedback-state" role="status">
          {submitStatus === "uploading"
            ? "正在保存录音"
            : voiceAssetId
              ? "录音已添加"
              : ""}
        </span>
        <button
          className="service-feedback-submit"
          type="button"
          aria-label="提交服务反馈"
          disabled={!canSubmit}
          onClick={() => void submit()}
        >
          <Send aria-hidden="true" />
          {submitStatus === "submitting" ? "正在提交" : "提交"}
        </button>
      </div>

      {submitStatus === "error" && voiceFile && !voiceAssetId ? (
        <button
          className="service-feedback-retry"
          type="button"
          onClick={() => void uploadVoice(voiceFile)}
        >
          <RefreshCw aria-hidden="true" />
          重新上传录音
        </button>
      ) : null}
      {voice.error || message ? (
        <p className="service-feedback-error" role="alert">
          {message || voice.error}
        </p>
      ) : null}
    </section>
  );
}
