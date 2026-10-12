import { useEffect, useState } from "react";
import { API_URL, MAKECODE_URL, SessionState, api, downloadLocalEvents, enqueue, flushQueue, makeEvent, queuedCount, saveLocalEvent, saveSnapshot } from "./api";
import { arrangeIdeas, steps } from "./tasks";
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
  const [ideaHints, setIdeaHints] = useState<Record<string, boolean>>({});
  const [participantInput, setParticipantInput] = useState("");
  const [saveMessage, setSaveMessage] = useState("");
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
    const save = () => { void saveNow(); };
    window.addEventListener("end-experiment", end);
    window.addEventListener("save-experiment", save);
    return () => { window.removeEventListener("end-experiment", end); window.removeEventListener("save-experiment", save); };
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
    try { await api(`/api/sessions/${next.sessionId}`, { method: "PATCH", body: JSON.stringify({ task_id: steps[next.stepIndex]?.taskId || "arrange", step_id: steps[next.stepIndex]?.id || null, state: { screen: next.screen, step_index: next.stepIndex, counts: next.counts, free_started_at: next.freeStartedAt } }) }); }
    catch { setSaved(false); }
  }
  async function start() {
    const requestedId = participantInput.trim();
    const offlineSession = (): SessionState => ({ sessionId: `local-${crypto.randomUUID()}`, participantId: requestedId || `LOCAL-${crypto.randomUUID().slice(0, 4).toUpperCase()}`, startedAt: new Date().toISOString(), screen: "intro", stepIndex: 0, counts: {}, offline: true });
    let next: SessionState;
    try {
      if (!connected) throw new Error("API offline");
      const data = await api<{ session_id: string; participant_id: string; started_at: string; export_dir: string }>("/api/sessions", { method: "POST", body: JSON.stringify({ participant_id: requestedId || null }) });
      next = { sessionId: data.session_id, participantId: data.participant_id, startedAt: data.started_at, screen: "intro", stepIndex: 0, counts: {}, exportDir: data.export_dir };
    } catch {
      next = offlineSession();
    }
    setSession(next); localStorage.setItem(SESSION_KEY, JSON.stringify(next)); await log("session_started", null, null, next.offline ? { mode: "local_test" } : {}, next);
  }
  async function saveNow() {
    if (!session) return;
    if (session.offline) { downloadLocalEvents(session.sessionId); setSaveMessage("ブラウザからJSONをダウンロードしました"); return; }
    try { await flushQueue(); const result = await saveSnapshot(session.sessionId); setSaveMessage(`${result.export_dir} に保存しました（${new Date(result.saved_at).toLocaleTimeString("ja-JP")}）`); }
    catch { downloadLocalEvents(session.sessionId); setSaveMessage("サーバーに保存できなかったため、ブラウザからJSONをダウンロードしました"); }
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
    if (!session || !freeIdea.trim()) return; const startedAt = new Date().toISOString(); const next = { ...session, freeStartedAt: startedAt, taskStartedAt: startedAt, freeIdea: freeIdea.trim() }; await saveProgress(next); await log("task_started", "arrange", null, {}, next); await log("arrange_idea_submitted", "arrange", null, { idea: freeIdea.trim() }, next); await log("arrange_started", "arrange", null, {}, next);
  }
  async function finish() {
    if (!session) return; await log("arrange_completed", "arrange", null, { idea: freeIdea, summary: freeSummary, completion_status: freeStatus, duration_ms: session.freeStartedAt ? Date.now() - Date.parse(session.freeStartedAt) : null }); await log("task_completed", "arrange", null); await endExperiment();
  }
  async function endExperiment() {
    if (!session) return;
    await log("session_completed", currentStep?.taskId || null, currentStep?.id || null, { completion_status: "manual_end" });
    let exportDir = session.exportDir;
    if (!session.offline) {
      try { await flushQueue(); exportDir = (await api<{ export_dir: string }>(`/api/sessions/${session.sessionId}/finish`, { method: "POST" })).export_dir; } catch { setSaved(false); }
    }
    const next = { ...session, screen: "done", freeIdea, freeSummary, freeStatus, exportDir };
    localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    await saveProgress(next);
    if (session.offline) downloadLocalEvents(session.sessionId);
  }
  const status = <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">{session && <span>参加者: <b className="font-mono text-slate-800">{session.participantId}</b></span>}<span>API: <b className={connected ? "text-emerald-700" : "text-amber-700"}>{connected ? "接続中" : "未接続"}</b></span><span>ログ: <b className={saved ? "text-emerald-700" : "text-amber-700"}>{session?.offline ? "ブラウザ保存" : saved ? "保存済み" : `未送信 ${queuedCount()}件`}</b></span>{saveMessage && <span className="text-emerald-700">{saveMessage}</span>}</div>;
  if (!session) return <Shell status={status}><div className="card mx-auto max-w-xl"><p className="mb-2 text-sm font-bold text-indigo-700">micro:bit プログラミング学習</p><h1 className="mb-3 text-3xl font-bold">学習実験を始めます</h1><p className="mb-6 text-slate-600">開始すると、この画面の操作とMakeCodeでの作業が自動で記録されます。</p><label className="mb-6 block font-semibold">参加者ID（空欄なら自動で決まります）<input className="field mt-2 font-mono" placeholder="例: P01" value={participantInput} pattern="[A-Za-z0-9_-]*" maxLength={40} onChange={(e) => setParticipantInput(e.target.value.replace(/[^A-Za-z0-9_-]/g, ""))} /></label><button className="btn btn-primary w-full" onClick={start}>開始</button>{!connected && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">APIに接続できません。このまま開始するとブラウザ内だけに保存され、MakeCodeの記録とは自動で結び付きません。</p>}</div></Shell>;
  if (session.screen === "intro") return <Shell status={status}><div className="card mx-auto max-w-3xl"><h1 className="mb-5 text-3xl font-bold">実験の進め方</h1><ol className="list-decimal space-y-3 pl-6 text-lg"><li><b>チュートリアル</b>：MakeCodeの基本操作に慣れます。</li><li><b>ゲーム制作</b>：micro:bitを傾けてボールをゴールまで動かすゲームを、順番に作ります。</li><li><b>自由アレンジ</b>：作ったゲームに、音やランダムなど好きな工夫を加えます。</li></ol><p className="mt-5 text-slate-600">必要なときだけヒント・解答を開いてください。できたら「完了して次へ」、未完成でも「未完了で次へ」で先へ進めます。</p><div className="mt-7 flex flex-wrap gap-3"><a className="btn" href={MAKECODE_URL} target="_blank" rel="noreferrer">MakeCodeを開く ↗</a><button className="btn btn-primary" onClick={beginTasks}>チュートリアルを始める</button></div></div></Shell>;
  if (session.screen === "free") return <Shell status={status}><div className="card mx-auto max-w-4xl"><Header title="自由アレンジ" estimate="20分" elapsed={elapsed} taskElapsed={session.taskStartedAt ? now - Date.parse(session.taskStartedAt) : undefined} /><h1 className="mt-6 text-3xl font-bold">ゲームを自由にアレンジしよう</h1><p className="mt-3 text-lg text-slate-600">作ったゲームに工夫を加えます。下の例から選んでも、自分で考えたアイデアでもかまいません。いくつ組み合わせてもOKです。</p><div className="mt-6 grid gap-4 md:grid-cols-2">{arrangeIdeas.map((idea) => <section key={idea.id} className="rounded-xl border border-slate-200 p-4"><h2 className="font-bold">{idea.title}</h2><p className="mt-1 text-slate-600">{idea.body}</p><div className="mt-3 flex flex-wrap gap-2">{!session.freeStartedAt && <button className="btn" onClick={() => { const text = freeIdea.trim() ? `${freeIdea.trim()}\n${idea.title}` : idea.title; setFreeIdea(text); setSession({ ...session, freeIdea: text }); void log("arrange_idea_selected", "arrange", null, { idea_id: idea.id }); }}>これをやってみる</button>}<button className="btn" onClick={() => { const open = !ideaHints[idea.id]; setIdeaHints({ ...ideaHints, [idea.id]: open }); void log(`arrange_hint_${open ? "opened" : "closed"}`, "arrange", null, { idea_id: idea.id }); }}>{ideaHints[idea.id] ? "ヒントを閉じる" : "ヒントを見る"}</button></div>{ideaHints[idea.id] && <p className="mt-3 rounded-lg bg-slate-50 p-3 leading-7">{idea.hint}</p>}</section>)}</div>{!session.freeStartedAt ? <div className="mt-8 space-y-4"><label className="block font-semibold">やってみたいアレンジ<textarea className="field mt-2 min-h-28" placeholder="例から選ぶか、自分のアイデアを書いてください" value={freeIdea} onChange={(e) => { setFreeIdea(e.target.value); setSession({ ...session, freeIdea: e.target.value }); }} /></label><button className="btn btn-primary" disabled={!freeIdea.trim()} onClick={startFree}>アレンジを始める</button></div> : <div className="mt-8 space-y-5"><p className="rounded-xl bg-indigo-50 p-4 font-semibold">アレンジ時間: {formatTime(now - Date.parse(session.freeStartedAt))}</p><p className="whitespace-pre-wrap rounded-xl bg-slate-50 p-4"><span className="block text-sm text-slate-500">やってみたいアレンジ</span>{session.freeIdea}</p><label className="block font-semibold">実際に作ったもの<textarea className="field mt-2 min-h-28" value={freeSummary} onChange={(e) => { setFreeSummary(e.target.value); setSession({ ...session, freeSummary: e.target.value }); }} /></label><label className="block font-semibold">完成状況<select className="field mt-2" value={freeStatus} onChange={(e) => { setFreeStatus(e.target.value); setSession({ ...session, freeStatus: e.target.value }); }}><option>完成</option><option>一部完成</option><option>未完成</option></select></label><button className="btn btn-primary" onClick={finish}>アレンジを終了して実験を終える</button></div>}</div></Shell>;
  if (session.screen === "done") return <Shell status={status}><div className="card mx-auto max-w-2xl text-center"><p className="mb-2 text-sm font-bold text-emerald-700">実験終了</p><h1 className="text-3xl font-bold">ご協力ありがとうございました</h1><dl className="my-7 space-y-3 rounded-xl bg-slate-50 p-5 text-left"><div><dt className="text-sm text-slate-500">参加者ID</dt><dd className="font-mono">{session.participantId}</dd></div><div><dt className="text-sm text-slate-500">保存先</dt><dd className="break-all font-mono text-sm">{session.offline ? "ブラウザ（ダウンロードしたJSON）" : `microbit-research-website/backend/${session.exportDir || "data/exports/sessions/"}`}</dd></div></dl>{session.offline && <p className="rounded-xl bg-amber-50 p-4 text-left text-amber-900">APIに接続していなかったため、MakeCodeの記録はEdit LoggerからJSONを出力して実験者へ渡してください。</p>}<button className="btn mt-4" onClick={() => downloadLocalEvents(session.sessionId)}>操作ログJSONをダウンロード</button><button className="btn mt-4 ml-3" onClick={() => { localStorage.removeItem(SESSION_KEY); location.reload(); }}>次の参加者を始める</button></div></Shell>;
  if (!currentStep) return null;
  return <Shell status={status}><div className="mx-auto max-w-5xl"><Header title={currentStep.taskTitle} estimate={currentStep.estimate} elapsed={elapsed} taskElapsed={session.taskStartedAt ? now - Date.parse(session.taskStartedAt) : undefined} stepElapsed={session.stepStartedAt ? now - Date.parse(session.stepStartedAt) : undefined} step={`${session.stepIndex + 1} / ${steps.length}`} /><div className="card mt-5"><p className="text-sm font-bold text-indigo-700">{currentStep.phase}・Step {currentStep.id}</p><h1 className="mt-2 text-3xl font-bold">{currentStep.title}</h1><p className="mt-5 text-xl leading-8">{currentStep.body}</p>{currentStep.image && <img className="mt-5 max-w-full rounded-xl" src={currentStep.image} alt="問題の参考画像" />}<div className="mt-6 rounded-xl bg-slate-50 p-5"><h2 className="font-bold">完了条件</h2><ul className="mt-2 list-disc space-y-1 pl-6">{currentStep.criteria.map((item) => <li key={item}>{item}</li>)}</ul></div><div className="mt-6 grid gap-4 md:grid-cols-2"><Help title="ヒント" open={hintOpen} onClick={() => toggleHelp("hint")}>{currentStep.hint}</Help><Help title="解答" open={answerOpen} onClick={() => toggleHelp("answer")}>{currentStep.answer}{currentStep.answerImage && <img className="mt-4 max-w-full rounded-xl" src={currentStep.answerImage} alt="解答の参考画像" />}</Help></div><div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-6"><div className="flex gap-3"><button className="btn" disabled={session.stepIndex === 0} onClick={() => move("back")}>前のステップ</button><a className="btn" href={MAKECODE_URL} target="_blank" rel="noreferrer">MakeCodeを開く ↗</a></div><div className="flex gap-3"><button className="btn btn-danger" onClick={() => move("next", false)}>未完了で次へ</button><button className="btn btn-primary" onClick={() => move("next", true)}>完了して次へ</button></div></div></div></div></Shell>;
}

function Shell({ children, status }: { children: React.ReactNode; status: React.ReactNode }) { const active = savedSession(); return <><header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4"><a href="/" className="font-bold">micro:bit 学習実験</a>{status}</div></header><main className="px-6 py-10">{children}</main>{active && active.screen !== "done" && <footer className="border-t border-slate-200 bg-white px-6 py-8 text-center"><div className="flex flex-wrap justify-center gap-3"><button className="btn" onClick={() => window.dispatchEvent(new Event("save-experiment"))}>ここまでのログを保存</button><button className="btn btn-danger" onClick={() => window.dispatchEvent(new Event("end-experiment"))}>実験を終了してデータを保存</button></div></footer>}</>; }
function Header({ title, estimate, elapsed, taskElapsed, stepElapsed, step }: { title: string; estimate: string; elapsed: number; taskElapsed?: number; stepElapsed?: number; step?: string }) { return <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-slate-900 px-6 py-4 text-white"><div><p className="text-sm text-slate-300">現在の課題</p><h2 className="text-xl font-bold">{title}</h2></div><div className="flex flex-wrap gap-6 text-sm">{step && <div><span className="block text-slate-400">ステップ</span><b>{step}</b></div>}<div><span className="block text-slate-400">目安</span><b>{estimate}</b></div><div><span className="block text-slate-400">全体</span><b className="font-mono">{formatTime(elapsed)}</b></div>{taskElapsed !== undefined && <div><span className="block text-slate-400">課題</span><b className="font-mono">{formatTime(taskElapsed)}</b></div>}{stepElapsed !== undefined && <div><span className="block text-slate-400">ステップ</span><b className="font-mono">{formatTime(stepElapsed)}</b></div>}</div></div>; }
function Help({ title, open, onClick, children }: { title: string; open: boolean; onClick: () => void; children: React.ReactNode }) { return <section className="rounded-xl border border-slate-200 p-4"><button className="btn w-full" onClick={onClick}>{open ? `${title}を閉じる` : `${title}を見る`}</button>{open && <p className="mt-4 leading-7">{children}</p>}</section>; }

