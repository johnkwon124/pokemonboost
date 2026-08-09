"use client";

import { useState } from "react";
import Scanner from "@/components/Scanner";
import CardResult from "@/components/CardResult";
import CandidatePicker from "@/components/CandidatePicker";
import { outcomeFromPick, type ScanChoices, type ScanOutcome } from "@/lib/scanFlow";
import type { Card, SessionScan } from "@/types/card";

export default function Home() {
  const [current, setCurrent] = useState<ScanOutcome | null>(null);
  const [choices, setChoices] = useState<ScanChoices | null>(null);
  const [session, setSession] = useState<SessionScan[]>([]);
  // Once the user has started the camera in this session, returning to the
  // scanner from a result auto-resumes — saves the extra "카메라 시작" tap.
  const [cameraReady, setCameraReady] = useState(false);

  const handleResult = (outcome: ScanOutcome) => {
    setCameraReady(true);
    setChoices(null);
    setCurrent(outcome);
    setSession((prev) => {
      if (prev[0]?.card.id === outcome.card.id) return prev;
      const entry: SessionScan = {
        key: `${outcome.card.id}-${Date.now()}`,
        card: outcome.card,
        analysis: outcome.analysis,
        at: Date.now()
      };
      return [entry, ...prev].slice(0, 30);
    });
  };

  const handleChoices = (c: ScanChoices) => {
    setCameraReady(true);
    setChoices(c);
  };

  const handlePick = (card: Card) => {
    handleResult(outcomeFromPick(card, choices?.matchedName ?? card.name));
  };

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between px-5 pb-3 pt-[max(env(safe-area-inset-top),1rem)]">
        <h1 className="text-lg font-semibold tracking-tight text-ink-100">PokeScan</h1>
        <span className="rounded-full border border-ink-700 px-2 py-0.5 text-[10px] uppercase tracking-wider text-ink-300">
          beta
        </span>
      </header>

      {choices ? (
        <CandidatePicker
          matchedName={choices.matchedName}
          lang={choices.lang}
          candidates={choices.candidates}
          onPick={handlePick}
          onCancel={() => setChoices(null)}
        />
      ) : current ? (
        <CardResult
          card={current.card}
          analysis={current.analysis}
          session={session}
          onBack={() => setCurrent(null)}
          onPickSession={(s) => setCurrent({ card: s.card, analysis: s.analysis, ocrText: "" })}
        />
      ) : (
        <Scanner
          onResult={handleResult}
          onChoices={handleChoices}
          sessionCount={session.length}
          autoStart={cameraReady}
        />
      )}
    </div>
  );
}
