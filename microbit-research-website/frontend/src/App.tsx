import { useEffect, useState } from "react";
import { API_URL, MAKECODE_URL, SessionState, api, downloadLocalEvents, enqueue, flushQueue, makeEvent, queuedCount, saveLocalEvent } from "./api";
import { ideaExamples, steps } from "./tasks";
import Admin from "./Admin";

const SESSION_KEY = "microbit-research:session";
const formatTime = (ms: number) => { const sec = Math.max(0, Math.floor(ms / 1000)); return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`; };
const savedSession = (): SessionState | null => { try { return JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); } catch { return null; } };

export default function App() {
  if (location.pathname.startsWith("/admin")) return <Admin />;
  const [session, setSession] = useState<SessionState | null>(savedSession);
  const [connected, setConnected] = useState(false);
  const [saved, setSaved] = useState(queuedCount() === 0);
  const [now, setNow] = useState(Date.now());
  const [hintOpen, setHintOpen] = useState(false);
  const [answerOpen, setAnswerOpen] = useState(false);
  const [freeIdea, setFreeIdea] = useState(() => savedSession()?.freeIdea || "");
  const [freeSummary, setFreeSummary] = useState(() => savedSession()?.freeSummary || "");
  const [freeStatus, setFreeStatus] = useState(() => savedSession()?.freeStatus || "完成");
  const [examplesOpen, setExamplesOpen] = useState(false);
  const currentStep = session ? steps[session.stepIndex] : undefined;
  const elapsed = session ? now - Date.parse(session.startedAt) : 0;

  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => { fetch(`${API_URL}/api/health`).then((r) => setConnected(r.ok)).catch(() => setConnected(false)); flushQueue().then((ok) => setSaved(ok && queuedCount() === 0)); }, []);
  useEffect(() => {
    const restored = savedSession();
    if (!restored || restored.screen === "done") return;
    void log("session_resumed", steps[restored.stepIndex]?.taskId || null, steps[restored.stepIndex]?.id || null, { screen: restored.screen }, restored);
    if (restored.screen === "steps" && steps[restored.stepIndex]) {
      void log("step_viewed", steps[restored.stepIndex].taskId, steps[restored.stepIndex].id, { visit: "reload" }, restored);
    }
  }, []);
  useEffect(() => { if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session)); }, [session]);
  useEffect(() => {
    if (!session || session.screen === "done") return;
    const end = () => { void endExperiment(); };
    window.addEventListener("end-experiment", end);
    return () => window.removeEventListener("end-experiment", end);
  }, [session]);
  useEffect(() => {
    if (!session || session.screen === "done") return;
    const visibility = () => log("page_visibility_changed", currentStep?.taskId || null, currentStep?.id || null, { visibility_state: document.visibilityState });
    const interrupted = () => { const event = makeEvent(session, "session_interrupted", currentStep?.taskId || null, currentStep?.id || null, { reason: "page_unload" }); saveLocalEvent(event); if (!session.offline) void enqueue(event); };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", interrupted);
    return () => { document.removeEventListener("visibilitychange", visibility); window.removeEventListener("pagehide", interrupted); };
  }, [session?.sessionId, session?.screen, session?.stepIndex]);

  async function log(type: string, taskId: string | null, stepId: string | null, metadata: Record<string, unknown> = {}, target = session) {
    if (!target) return;
    const event = makeEvent(target, type, taskId, stepId, metadata);
    saveLocalEvent(event);
    if (target.offline) { setSaved(true); return; }
    setSaved(false); const ok = await enqueue(event); setSaved(ok && queuedCount() === 0);
  }
  async function saveProgress(next: SessionState) {
    setSession(next);
    if (next.offline) return;
    try { await api(`/api/sessions/${next.sessionId}`, { method: "PATCH", body: JSON.stringify({ task_id: steps[next.stepIndex]?.taskId || "free-creation", step_id: steps[next.stepIndex]?.id || null, state: { screen: next.screen, step_index: next.stepIndex, counts: next.counts, free_started_at: next.freeStartedAt } }) }); }
    catch { setSaved(false); }
  }
  async function start() {
    const participantId = `TEST-${crypto.randomUUID().slice(0, 6).toUpperCase()}`;
    if (!connected) {
      const startedAt = new Date().toISOString();
      const next: SessionState = { sessionId: `test-${crypto.randomUUID()}`, participantId, startedAt, screen: "intro", stepIndex: 0, counts: {}, offline: true };
      setSession(next); localStorage.setItem(SESSION_KEY, JSON.stringify(next)); await log("session_started", null, null, { mode: "local_test" }, next); return;
    }
    try {
      const data = await api<{ session_id: string; started_at: string }>("/api/sessions", { method: "POST", body: JSON.stringify({ participant_id: participantId }) });
      const next = { sessionId: data.session_id, participantId, startedAt: data.started_at, screen: "intro", stepIndex: 0, counts: {} };
      setSession(next); localStorage.setItem(SESSION_KEY, JSON.stringify(next)); await log("session_started", null, null, {}, next);
    } catch {
      const startedAt = new Date().toISOString();
      const next: SessionState = { sessionId: `test-${crypto.randomUUID()}`, participantId, startedAt, screen: "intro", stepIndex: 0, counts: {}, offline: true };
      setSession(next); localStorage.setItem(SESSION_KEY, JSON.stringify(next)); await log("session_started", null, null, { mode: "local_test" }, next);
    }
  }
  async function beginTasks() {
    if (!session) return; const startedAt = new Date().toISOString(); const next = { ...session, screen: "steps", taskStartedAt: startedAt, stepStartedAt: startedAt }; await saveProgress(next); await log("task_started", steps[0].taskId, steps[0].id, {}, next); await log("step_viewed", steps[0].taskId, steps[0].id, { visit: "first" }, next);
  }
  async function move(direction: "next" | "back", completed = true) {
    if (!session || !currentStep) return;
    if (direction === "back") {
      const index = Math.max(0, session.stepIndex - 1); const next = { ...session, stepIndex: index, stepStartedAt: new Date().toISOString() };
      setHintOpen(false); setAnswerOpen(false); await saveProgress(next); await log("step_navigated", steps[index].taskId, steps[index].id, { from_step: currentStep.id, to_step: steps[index].id, direction }, next); await log("step_viewed", steps[index].taskId, steps[index].id, { visit: "return" }, next); return;
    }
    const stepDuration = session.stepStartedAt ? Date.now() - Date.parse(session.stepStartedAt) : null;
    await log(completed ? "step_completed" : "step_skipped", currentStep.taskId, currentStep.id, completed ? { completion_status: "self_reported", duration_ms: stepDuration } : { reason: "unfinished", duration_ms: stepDuration });
    const index = session.stepIndex + 1;
    if (index >= steps.length) { await log("task_completed", currentStep.taskId, currentStep.id, { duration_ms: session.taskStartedAt ? Date.now() - Date.parse(session.taskStartedAt) : null }); const next = { ...session, screen: "free", taskStartedAt: undefined, stepStartedAt: undefined }; await saveProgress(next); return; }
    const nextStep = steps[index]; const changedTask = nextStep.taskId !== currentStep.taskId; const changedAt = new Date().toISOString(); const next = { ...session, stepIndex: index, stepStartedAt: changedAt, taskStartedAt: changedTask ? changedAt : session.taskStartedAt };
    if (changedTask) { await log("task_completed", currentStep.taskId, currentStep.id, { duration_ms: session.taskStartedAt ? Date.now() - Date.parse(session.taskStartedAt) : null }); await log("task_started", nextStep.taskId, nextStep.id, {}, next); }
    setHintOpen(false); setAnswerOpen(false); await saveProgress(next); await log("step_navigated", nextStep.taskId, nextStep.id, { from_step: currentStep.id, to_step: nextStep.id, direction, completion_status: completed ? "completed" : "unfinished" }, next); await log("step_viewed", nextStep.taskId, nextStep.id, { visit: "first" }, next);
  }
  async function toggleHelp(kind: "hint" | "answer") {
    if (!session || !currentStep) return; const open = kind === "hint" ? !hintOpen : !answerOpen; const key = `${currentStep.id}:${kind}`; const count = open ? (session.counts[key] || 0) + 1 : session.counts[key] || 0; const next = open ? { ...session, counts: { ...session.counts, [key]: count } } : session;
    if (kind === "hint") setHintOpen(open); else setAnswerOpen(open); if (open) setSession(next);
    await log(`${kind}_${open ? "opened" : "closed"}`, currentStep.taskId, currentStep.id, { [`${kind}_id`]: `${currentStep.id}-${kind}`, open_count: count }, next);
  }
  async function startFree() {
    if (!session || !freeIdea.trim()) return; const startedAt = new Date().toISOString(); const next = { ...session, freeStartedAt: startedAt, taskStartedAt: startedAt, freeIdea: freeIdea.trim() }; await saveProgress(next); await log("task_started", "free-creation", null, {}, next); await log("free_creation_idea_submitted", "free-creation", null, { idea: freeIdea.trim() }, next); await log("free_creation_started", "free-creation", null, {}, next);
  }
  async function finish() {
    if (!session) return; await log("free_creation_completed", "free-creation", null, { idea: freeIdea, summary: freeSummary, completion_status: freeStatus, duration_ms: session.freeStartedAt ? Date.now() - Date.parse(session.freeStartedAt) : null }); await log("task_completed", "free-creation", null); await endExperiment();
  }
  async function endExperiment() {
    if (!session) return;
    await log("session_completed", currentStep?.taskId || null, currentStep?.id || null, { completion_status: "manual_end" });
    if (!session.offline) {
      try { await api(`/api/sessions/${session.sessionId}/finish`, { method: "POST" }); } catch { setSaved(false); }
    }
    const next = { ...session, screen: "done", freeIdea, freeSummary, freeStatus };
    localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    await saveProgress(next);
    downloadLocalEvents(session.sessionId);
  }
  const status = <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">{session && <span>接続ID: <button className="rounded bg-indigo-50 px-2 py-1 font-mono font-bold text-indigo-700" title="クリックしてコピー" onClick={() => navigator.clipboard.writeText(session.participantId)}>{session.participantId}</button></span>}<span>API: <b className={connected ? "text-emerald-700" : "text-amber-700"}>{connected ? "接続中" : "未接続"}</b></span><span>ログ: <b className={saved ? "text-emerald-700" : "text-amber-700"}>{session?.offline ? "ブラウザ保存" : saved ? "保存済み" : `未送信 ${queuedCount()}件`}</b></span></div>;
  if (!session) return <Shell status={status}><div className="card mx-auto max-w-xl text-center"><p className="mb-2 text-sm font-bold text-indigo-700">micro:bit プログラミング学習</p><h1 className="mb-3 text-3xl font-bold">学習実験を始めます</h1><p className="mb-7 text-slate-600">操作内容と時刻は、このブラウザにも保存されます。</p><button className="btn btn-primary w-full" onClick={start}>開始</button></div></Shell>;
  if (session.screen === "intro") return <Shell status={status}><div className="card mx-auto max-w-3xl"><h1 className="mb-5 text-3xl font-bold">実験の進め方</h1><ol className="list-decimal space-y-3 pl-6 text-lg"><li>MakeCodeを別タブで開きます。</li><li>Edit Loggerを準備して記録を開始します。</li><li>この画面の問題を確認し、課題ごとにプログラムを作ります。</li><li>必要なときだけヒント・解答を開きます。</li><li>できたら「完了して次へ」を押します。未完成でも先へ進めます。</li></ol><div className="mt-7 flex flex-wrap gap-3"><a className="btn" href={MAKECODE_URL} target="_blank" rel="noreferrer">MakeCodeを開く ↗</a><button className="btn btn-primary" onClick={beginTasks}>問題を始める</button></div></div></Shell>;
  if (session.screen === "free") return <Shell status={status}><div className="card mx-auto max-w-3xl"><Header title="自由制作" estimate="15分" elapsed={elapsed} taskElapsed={session.taskStartedAt ? now - Date.parse(session.taskStartedAt) : undefined} /><h1 className="mt-6 text-3xl font-bold">自由に作品を作ろう</h1>{!session.freeStartedAt ? <div className="mt-6 space-y-4"><label className="block font-semibold">作りたいもの<textarea className="field mt-2 min-h-28" value={freeIdea} onChange={(e) => { setFreeIdea(e.target.value); setSession({ ...session, freeIdea: e.target.value }); }} /></label><button className="btn btn-primary" disabled={!freeIdea.trim()} onClick={startFree}>自由制作を開始する</button></div> : <div className="mt-6 space-y-5"><p className="rounded-xl bg-indigo-50 p-4 font-semibold">制作時間: {formatTime(now - Date.parse(session.freeStartedAt))}</p><button className="btn" onClick={async () => { const open = !examplesOpen; setExamplesOpen(open); await log(`free_creation_example_${open ? "opened" : "closed"}`, "free-creation", null, { examples: ideaExamples }); }}>{examplesOpen ? "アイデア例を閉じる" : "アイデア例を見る"}</button>{examplesOpen && <ul className="list-disc rounded-xl bg-slate-50 p-5 pl-10">{ideaExamples.map((idea) => <li key={idea}>{idea}</li>)}</ul>}<label className="block font-semibold">作品の概要<textarea className="field mt-2 min-h-28" value={freeSummary} onChange={(e) => { setFreeSummary(e.target.value); setSession({ ...session, freeSummary: e.target.value }); }} /></label><label className="block font-semibold">完成状況<select className="field mt-2" value={freeStatus} onChange={(e) => { setFreeStatus(e.target.value); setSession({ ...session, freeStatus: e.target.value }); }}><option>完成</option><option>一部完成</option><option>未完成</option></select></label><button className="btn btn-primary" onClick={finish}>制作を終了して実験を終える</button></div>}</div></Shell>;
  if (session.screen === "done") return <Shell status={status}><div className="card mx-auto max-w-2xl text-center"><p className="mb-2 text-sm font-bold text-emerald-700">実験終了</p><h1 className="text-3xl font-bold">ご協力ありがとうございました</h1><dl className="my-7 space-y-3 rounded-xl bg-slate-50 p-5 text-left"><div><dt className="text-sm text-slate-500">参加者ID</dt><dd className="font-mono">{session.participantId}</dd></div><div><dt className="text-sm text-slate-500">セッションID</dt><dd className="break-all font-mono text-sm">{session.sessionId}</dd></div></dl><p className="rounded-xl bg-amber-50 p-4 text-left text-amber-900">MakeCodeのEdit LoggerからJSONを出力し、実験者へ渡してください。</p><button className="btn mt-4" onClick={() => downloadLocalEvents(session.sessionId)}>操作ログJSONを保存する</button><button className="btn mt-4 ml-3" onClick={() => { localStorage.removeItem(SESSION_KEY); location.reload(); }}>最初からテストする</button></div></Shell>;
  if (!currentStep) return null;
  return <Shell status={status}><div className="mx-auto max-w-5xl"><Header title={currentStep.taskTitle} estimate={currentStep.estimate} elapsed={elapsed} taskElapsed={session.taskStartedAt ? now - Date.parse(session.taskStartedAt) : undefined} stepElapsed={session.stepStartedAt ? now - Date.parse(session.stepStartedAt) : undefined} step={`${session.stepIndex + 1} / ${steps.length}`} /><div className="card mt-5"><p className="text-sm font-bold text-indigo-700">{currentStep.phase}・Step {currentStep.id}</p><h1 className="mt-2 text-3xl font-bold">{currentStep.title}</h1><p className="mt-5 text-xl leading-8">{currentStep.body}</p>{currentStep.image && <img className="mt-5 max-w-full rounded-xl" src={currentStep.image} alt="問題の参考画像" />}<div className="mt-6 rounded-xl bg-slate-50 p-5"><h2 className="font-bold">完了条件</h2><ul className="mt-2 list-disc space-y-1 pl-6">{currentStep.criteria.map((item) => <li key={item}>{item}</li>)}</ul></div><div className="mt-6 grid gap-4 md:grid-cols-2"><Help title="ヒント" open={hintOpen} onClick={() => toggleHelp("hint")}>{currentStep.hint}</Help><Help title="解答" open={answerOpen} onClick={() => toggleHelp("answer")}>{currentStep.answer}{currentStep.answerImage && <img className="mt-4 max-w-full rounded-xl" src={currentStep.answerImage} alt="解答の参考画像" />}</Help></div><div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-6"><div className="flex gap-3"><button className="btn" disabled={session.stepIndex === 0} onClick={() => move("back")}>前のステップ</button><a className="btn" href={MAKECODE_URL} target="_blank" rel="noreferrer">MakeCodeを開く ↗</a></div><div className="flex gap-3"><button className="btn btn-danger" onClick={() => move("next", false)}>未完了で次へ</button><button className="btn btn-primary" onClick={() => move("next", true)}>完了して次へ</button></div></div></div></div></Shell>;
}

function Shell({ children, status }: { children: React.ReactNode; status: React.ReactNode }) { const active = savedSession(); return <><header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4"><a href="/" className="font-bold">micro:bit 学習実験</a>{status}</div></header><main className="px-6 py-10">{children}</main>{active && active.screen !== "done" && <footer className="border-t border-slate-200 bg-white px-6 py-8 text-center"><div className="flex flex-wrap justify-center gap-3"><button className="btn" onClick={() => downloadLocalEvents(active.sessionId)}>ここまでのログを保存</button><button className="btn btn-danger" onClick={() => window.dispatchEvent(new Event("end-experiment"))}>実験を終了してデータを保存</button></div></footer>}</>; }
function Header({ title, estimate, elapsed, taskElapsed, stepElapsed, step }: { title: string; estimate: string; elapsed: number; taskElapsed?: number; stepElapsed?: number; step?: string }) { return <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-slate-900 px-6 py-4 text-white"><div><p className="text-sm text-slate-300">現在の課題</p><h2 className="text-xl font-bold">{title}</h2></div><div className="flex flex-wrap gap-6 text-sm">{step && <div><span className="block text-slate-400">ステップ</span><b>{step}</b></div>}<div><span className="block text-slate-400">目安</span><b>{estimate}</b></div><div><span className="block text-slate-400">全体</span><b className="font-mono">{formatTime(elapsed)}</b></div>{taskElapsed !== undefined && <div><span className="block text-slate-400">課題</span><b className="font-mono">{formatTime(taskElapsed)}</b></div>}{stepElapsed !== undefined && <div><span className="block text-slate-400">ステップ</span><b className="font-mono">{formatTime(stepElapsed)}</b></div>}</div></div>; }
function Help({ title, open, onClick, children }: { title: string; open: boolean; onClick: () => void; children: React.ReactNode }) { return <section className="rounded-xl border border-slate-200 p-4"><button className="btn w-full" onClick={onClick}>{open ? `${title}を閉じる` : `${title}を見る`}</button>{open && <p className="mt-4 leading-7">{children}</p>}</section>; }

