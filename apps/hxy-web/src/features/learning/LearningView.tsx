import {
  AlertCircle,
  Clock3,
  LockKeyhole,
  Mic,
  RefreshCw,
  Send,
  Square,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import type {
  LearningClient,
  LearningHome,
  LearningPracticeResult,
} from "../../api/learning";


interface SpeechResultLike {
  transcript: string;
}

interface SpeechEventLike {
  results: ArrayLike<ArrayLike<SpeechResultLike>>;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

function speechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  const browser = globalThis as typeof globalThis & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };
  return browser.SpeechRecognition ?? browser.webkitSpeechRecognition ?? null;
}

function progressLabel(count: number) {
  return `已练习 ${count} 次`;
}

export function LearningView({ client }: { client: LearningClient }) {
  const [home, setHome] = useState<LearningHome | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<LearningPracticeResult | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [submitting, setSubmitting] = useState(false);
  const [listening, setListening] = useState(false);
  const [message, setMessage] = useState("");
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setMessage("");
    try {
      setHome(await client.loadLearning());
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, [client]);

  useEffect(() => {
    void load();
    return () => recognitionRef.current?.stop();
  }, [load]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const employeeAnswer = answer.trim();
    if (!home || !employeeAnswer || submitting) return;
    setSubmitting(true);
    setMessage("");
    try {
      const response = await client.submitPractice({
        action_id: home.next_action.id,
        employee_answer: employeeAnswer,
      });
      setResult(response);
      setHome(response);
      setAnswer("");
    } catch {
      setMessage("练习没有提交成功，请重试");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleSpeech = () => {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const Constructor = speechRecognitionConstructor();
    if (!Constructor) return;
    const recognition = new Constructor();
    recognition.lang = "zh-CN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) setAnswer((current) => `${current} ${transcript}`.trim());
    };
    recognition.onerror = () => {
      setMessage("没有听清，请再说一次或直接输入文字");
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  };

  if (status === "loading") {
    return (
      <section className="frontstage-view learning-view" aria-label="学习">
        <div className="quiet-state" role="status">正在准备下一项练习</div>
      </section>
    );
  }

  if (status === "error" || !home) {
    return (
      <section className="frontstage-view learning-view" aria-label="学习">
        <div className="quiet-state" role="alert">
          <AlertCircle aria-hidden="true" />
          <p>学习内容暂时没有加载出来</p>
          <button type="button" onClick={() => void load()}>
            <RefreshCw aria-hidden="true" />
            重新加载
          </button>
        </div>
      </section>
    );
  }

  const action = home.next_action;
  const progress = home.progress;
  const canUseVoice =
    action.response_modes.includes("voice") && speechRecognitionConstructor() !== null;

  return (
    <section className="frontstage-view learning-view" aria-label="学习">
      <header className="view-header learning-header">
        <div>
          <h1>学习</h1>
          <p>只练现在最需要的一项。</p>
        </div>
        <span className="private-progress-label">
          <LockKeyhole aria-hidden="true" />
          仅自己可见
        </span>
      </header>

      <div className="learning-action">
        <div className="learning-action-heading">
          <div>
            <h2>{action.title}</h2>
            <p>{action.purpose}</p>
          </div>
          <span>
            <Clock3 aria-hidden="true" />
            约 {action.estimated_minutes} 分钟
          </span>
        </div>

        <blockquote>{action.scenario.customer_message}</blockquote>

        <form className="learning-practice-form" onSubmit={(event) => void submit(event)}>
          <label htmlFor="learning-answer">你会怎么回应？</label>
          <textarea
            id="learning-answer"
            rows={4}
            maxLength={4000}
            value={answer}
            disabled={submitting}
            onChange={(event) => setAnswer(event.target.value)}
          />
          <div className="learning-practice-actions">
            {canUseVoice ? (
              <button
                className={`learning-voice-button${listening ? " is-listening" : ""}`}
                type="button"
                aria-label={listening ? "停止语音输入" : "语音输入"}
                title={listening ? "停止语音输入" : "语音输入"}
                disabled={submitting}
                onClick={toggleSpeech}
              >
                {listening ? <Square aria-hidden="true" /> : <Mic aria-hidden="true" />}
              </button>
            ) : null}
            <button
              className="learning-submit-button"
              type="submit"
              disabled={submitting || !answer.trim()}
            >
              <Send aria-hidden="true" />
              {submitting ? "正在评估" : "提交练习"}
            </button>
          </div>
          {message ? <p className="learning-form-error" role="alert">{message}</p> : null}
        </form>
      </div>

      {result ? (
        <section className="learning-feedback" aria-labelledby="learning-feedback-title">
          <div className="learning-feedback-heading">
            <h2 id="learning-feedback-title">本次反馈</h2>
            <span>{result.attempt.score} 分</span>
          </div>
          {result.attempt.correction_points.length ? (
            <ul>
              {result.attempt.correction_points.map((point) => <li key={point}>{point}</li>)}
            </ul>
          ) : (
            <p>这次表达没有发现明显风险。</p>
          )}
          {result.attempt.standard_script ? (
            <div className="learning-example">
              <strong>可以这样说</strong>
              <p>{result.attempt.standard_script}</p>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="learning-progress" aria-label="个人学习进度">
        <div>
          <strong>{progressLabel(progress.attempts)}</strong>
          <span>正在练习：{progress.practicing.join("、")}</span>
        </div>
        {progress.needs_attention.length ? (
          <p>需要注意：{progress.needs_attention.join("；")}</p>
        ) : null}
      </section>

      <p className="learning-limitation">{home.limitations[1]}</p>
    </section>
  );
}
