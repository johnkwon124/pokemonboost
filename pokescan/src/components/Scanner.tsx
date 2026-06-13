"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ocrCardNumber, lookupCard, scanImage, ScanNotFoundError, type ScanOutcome } from "@/lib/scanFlow";

type ScanState = "idle" | "starting" | "scanning" | "busy" | "error";

const SCAN_INTERVAL_MS = 600;
const SCAN_MAX_ATTEMPTS = 12;
// average per-channel pixel delta below which we treat the frame as "held still"
const STILL_THRESHOLD = 18;
// if the frame never settles, capture anyway after this many consecutive shaky ticks
const FORCE_AFTER_SHAKY_TICKS = 3;

interface Props {
  onResult: (outcome: ScanOutcome) => void;
  sessionCount: number;
  // When true, start the camera on mount instead of waiting for the button —
  // used after the first successful scan so subsequent rescans are one-tap.
  autoStart?: boolean;
}

// Card-shaped guide the user aims with (fraction of frame).
const CARD = { x: 0.08, w: 0.84, top: 0.06, h: 0.88 };
// We OCR only the bottom band of the card — that's where the collector number
// and set total live (e.g. 025/198). Reading just this strip avoids the text
// noise of the whole card and keeps the number legible.
const BAND = { x: CARD.x, w: CARD.w, top: CARD.top + CARD.h * 0.8, h: CARD.h * 0.2 };
const MAX_UPLOAD_DIM = 1600;

export default function Scanner({ onResult, sessionCount, autoStart = false }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sampleRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);
  const attemptsRef = useRef(0);
  const prevSampleRef = useRef<Uint8ClampedArray | null>(null);
  const shakyTicksRef = useRef(0);
  const inFlightRef = useRef(false);
  // last collector number read by OCR; we commit only when two reads agree
  const lastReadRef = useRef<string | null>(null);

  const [state, setState] = useState<ScanState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState("카드 하단의 번호(예: 025/198)를 노란 띠에 맞추고 잠시 멈추세요");

  const stopStream = useCallback(() => {
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => stopStream(), [stopStream]);

  const bandRect = (w: number, h: number) => ({
    x: Math.floor(w * BAND.x),
    y: Math.floor(h * BAND.top),
    w: Math.floor(w * BAND.w),
    h: Math.floor(h * BAND.h)
  });

  // cheap motion gate so we only spend an OCR call when the user holds steady
  const frameIsSteady = useCallback((): boolean => {
    const video = videoRef.current;
    const sample = sampleRef.current;
    if (!video || !sample || video.readyState < 2) return false;
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) return false;
    const r = bandRect(vw, vh);
    const sw = 32;
    const sh = Math.max(8, Math.round((r.h / r.w) * sw));
    sample.width = sw;
    sample.height = sh;
    const ctx = sample.getContext("2d", { willReadFrequently: true });
    if (!ctx) return false;
    ctx.drawImage(video, r.x, r.y, r.w, r.h, 0, 0, sw, sh);
    const data = ctx.getImageData(0, 0, sw, sh).data;
    const prev = prevSampleRef.current;
    prevSampleRef.current = new Uint8ClampedArray(data);
    if (!prev || prev.length !== data.length) return false;
    let diff = 0;
    for (let i = 0; i < data.length; i += 4) {
      diff += Math.abs(data[i] - prev[i]) + Math.abs(data[i + 1] - prev[i + 1]) + Math.abs(data[i + 2] - prev[i + 2]);
    }
    return diff / (data.length / 4) / 3 < STILL_THRESHOLD;
  }, []);

  const captureBand = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) return null;
    const r = bandRect(vw, vh);
    const scale = Math.min(1, MAX_UPLOAD_DIM / Math.max(r.w, r.h));
    const outW = Math.round(r.w * scale);
    const outH = Math.round(r.h * scale);
    canvas.width = outW;
    canvas.height = outH;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, r.x, r.y, r.w, r.h, 0, 0, outW, outH);
    return canvas.toDataURL("image/jpeg", 0.9).split(",")[1] ?? null;
  }, []);

  const captureFull = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.92).split(",")[1] ?? null;
  }, []);

  // auto path: OCR the band, require two consecutive agreeing reads, then look up
  const processAuto = useCallback(
    async (base64: string) => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      setState("busy");
      try {
        const parsed = await ocrCardNumber(base64);
        if (!parsed) {
          setHint("번호가 안 보여요. 번호(025/198)를 노란 띠에 또렷하게 맞춰주세요");
          setState("scanning");
          return;
        }
        if (parsed.raw === lastReadRef.current) {
          // two reads agree → trust it and resolve
          setHint("조회 중…");
          const outcome = await lookupCard(parsed);
          if (outcome) {
            stopStream();
            onResult(outcome);
          } else {
            lastReadRef.current = null;
            setHint(`${parsed.raw} 번호의 카드를 DB에서 못 찾았어요. 번호를 다시 비춰주세요`);
            setState("scanning");
          }
        } else {
          // first sighting — wait for a confirming read
          lastReadRef.current = parsed.raw;
          setHint(`번호 확인 중… (${parsed.raw}) 그대로 멈춰주세요`);
          setState("scanning");
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "오류가 발생했습니다");
        setState("error");
      } finally {
        inFlightRef.current = false;
      }
    },
    [onResult, stopStream]
  );

  // manual path: user pressed the button — OCR the full frame and resolve in one shot
  const manualShot = useCallback(async () => {
    if (inFlightRef.current) return;
    const b64 = captureFull();
    if (!b64) return;
    inFlightRef.current = true;
    setState("busy");
    setHint("사진으로 인식 중…");
    try {
      const outcome = await scanImage(b64);
      stopStream();
      onResult(outcome);
    } catch (e) {
      if (e instanceof ScanNotFoundError) {
        setHint("번호를 찾지 못했어요. 카드 하단 번호가 또렷하게 나오도록 다시 시도해주세요");
        setState("scanning");
      } else {
        setError(e instanceof Error ? e.message : "오류가 발생했습니다");
        setState("error");
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [captureFull, onResult, stopStream]);

  const tick = useCallback(() => {
    if (inFlightRef.current) return;
    if (attemptsRef.current >= SCAN_MAX_ATTEMPTS) {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setHint("자동 인식이 안 되네요. '사진으로 시도'를 누르거나 카메라를 다시 시작하세요");
      return;
    }
    if (frameIsSteady()) {
      shakyTicksRef.current = 0;
    } else {
      shakyTicksRef.current += 1;
      if (shakyTicksRef.current < FORCE_AFTER_SHAKY_TICKS) return;
      shakyTicksRef.current = 0;
    }
    attemptsRef.current += 1;
    const b64 = captureBand();
    if (b64) void processAuto(b64);
  }, [frameIsSteady, captureBand, processAuto]);

  const cameraErrorMessage = (e: unknown): string => {
    if (e instanceof DOMException) {
      if (e.name === "NotAllowedError")
        return "카메라 권한이 거부되었어요. iOS 설정 → Safari → 카메라에서 허용으로 바꾸고 다시 시도하세요.";
      if (e.name === "NotFoundError") return "카메라를 찾을 수 없습니다.";
      if (e.name === "NotReadableError") return "다른 앱이 카메라를 사용 중입니다.";
    }
    return e instanceof Error ? e.message : "카메라에 접근할 수 없습니다";
  };

  const start = useCallback(async () => {
    setError(null);
    setState("starting");
    attemptsRef.current = 0;
    shakyTicksRef.current = 0;
    prevSampleRef.current = null;
    lastReadRef.current = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false
      });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) return;
      video.srcObject = stream;
      await video.play();
      setState("scanning");
      setHint("카드 하단의 번호(예: 025/198)를 노란 띠에 맞추고 잠시 멈추세요");
      intervalRef.current = window.setInterval(tick, SCAN_INTERVAL_MS);
    } catch (e) {
      setError(cameraErrorMessage(e));
      setState("error");
    }
  }, [tick]);

  // Auto-start the camera on mount when coming back from a result, so the user
  // doesn't have to tap "카메라 시작" again. The permission is already granted in
  // this session, so getUserMedia returns immediately.
  useEffect(() => {
    if (autoStart) void start();
    // We only want this to fire on the first mount; subsequent re-renders
    // (e.g. state changes) shouldn't restart the camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-1 flex-col">
      <div className="relative aspect-[3/4] w-full overflow-hidden rounded-b-3xl bg-black">
        <video ref={videoRef} playsInline muted className="absolute inset-0 h-full w-full object-cover" />
        <canvas ref={canvasRef} className="hidden" />
        <canvas ref={sampleRef} className="hidden" />

        {state === "idle" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
            <p className="text-sm text-ink-300">아이폰을 카드에 비추면 자동으로 인식해요</p>
            <button
              onClick={start}
              className="rounded-full bg-accent px-6 py-3 text-sm font-semibold text-ink-950 shadow-lg shadow-accent/20 active:scale-95"
            >
              카메라 시작
            </button>
          </div>
        )}

        {state !== "idle" && state !== "error" && (
          <div className="pointer-events-none absolute inset-0">
            {/* card-shaped aiming guide */}
            <div className="absolute inset-x-[8%] inset-y-[6%]">
              <div className="h-full w-full rounded-xl border-2 border-ink-200/60 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]" />
            </div>
            {/* bottom band = where the number is read; keep the card number here */}
            <div className="absolute left-[8%] right-[8%] h-[17.6%]" style={{ top: `${BAND.top * 100}%` }}>
              <div className="flex h-full w-full items-center justify-center rounded-md border-2 border-accent">
                <span className="rounded bg-black/55 px-2 py-0.5 text-[10px] text-accent-soft">카드 번호를 여기에</span>
              </div>
            </div>
            <div className="absolute left-1/2 top-6 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-[11px] font-medium tracking-wide text-ink-100">
              {state === "starting" && "카메라 준비 중…"}
              {state === "scanning" && "스캔 중…"}
              {state === "busy" && "인식 중…"}
            </div>
          </div>
        )}

        {state === "error" && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/70 px-6 text-center">
            <p className="text-sm text-ink-200">{error}</p>
          </div>
        )}
      </div>

      <div className="flex flex-col items-center gap-3 px-5 py-4 text-center">
        {state !== "idle" && state !== "error" && <p className="text-sm text-ink-300">{hint}</p>}
        {(state === "scanning" || state === "busy") && (
          <button
            onClick={manualShot}
            disabled={state === "busy"}
            className="rounded-full border border-ink-600 px-5 py-2 text-sm font-medium text-ink-100 disabled:opacity-50 active:scale-95"
          >
            사진으로 시도
          </button>
        )}
        {state === "error" && (
          <button onClick={start} className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-ink-950 active:scale-95">
            다시 시도
          </button>
        )}
        {sessionCount > 0 && state !== "idle" && <p className="text-[11px] text-ink-500">이번 세션 {sessionCount}장 스캔됨</p>}
      </div>
    </div>
  );
}
