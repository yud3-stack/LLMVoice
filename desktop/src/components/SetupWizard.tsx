import { useCallback, useEffect, useState } from "react";
import { Check, CircleAlert, Download, LoaderCircle } from "lucide-react";
import { useSetup, useSetupLog, type EnvironmentStatus } from "../hooks/useTauriCommands";
import type { Translation } from "../i18n";

type Props = { t: Translation; onReady: () => void };

export function SetupWizard({ t, onReady }: Props) {
  const { checkEnvironment, installRuntime, downloadModel } = useSetup();
  const [status, setStatus] = useState<EnvironmentStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [logs, setLogs] = useState<string[]>([]);

  const refresh = useCallback(async () => {
    try {
      const next = await checkEnvironment();
      setStatus(next);
      if (next.runtime && next.ffmpeg && next.ffprobe && next.model) {
        onReady();
      }
    } catch (error) {
      setMessage(String(error));
    }
  }, [checkEnvironment, onReady]);

  useEffect(() => { void refresh(); }, [refresh]);
  useSetupLog(useCallback((line) => setLogs((current) => [...current.slice(-39), line]), []));

  const startInstall = async () => {
    setBusy(true);
    setMessage("");
    setLogs([]);
    try {
      await installRuntime();
      await refresh();
    } catch (error) {
      setMessage(String(error));
    } finally {
      setBusy(false);
    }
  };

  const startModelDownload = async () => {
    setBusy(true);
    setMessage("");
    setLogs([]);
    try {
      await downloadModel();
      await refresh();
    } catch (error) {
      setMessage(String(error));
    } finally {
      setBusy(false);
    }
  };

  const prerequisitesReady = status?.runtime && status.ffmpeg && status.ffprobe;
  const ready = prerequisitesReady && status?.model;
  return (
    <div className="setup-overlay">
      <section className="setup-wizard" aria-busy={busy}>
        <span className="modal-kicker">{t.setupKicker}</span>
        <h1>{t.setupTitle}</h1>
        <p>{t.setupDescription}</p>
        <div className="setup-checks">
          <CheckRow label={t.setupRuntime} ready={Boolean(status?.runtime)} detail={status?.runtime_version} />
          <CheckRow label={t.setupFfmpeg} ready={Boolean(status?.ffmpeg && status?.ffprobe)} detail={status?.ffmpeg && status?.ffprobe ? t.setupInstalled : t.setupMissing} />
          <CheckRow label={t.setupModel} ready={Boolean(status?.model)} detail={status?.model ? t.setupInstalled : t.setupModelLater} />
        </div>
        {message && <div className="setup-error"><CircleAlert size={16} />{message}</div>}
        {logs.length > 0 && <div className="setup-log">{logs.map((line, index) => <div key={`${index}-${line}`}>{line}</div>)}</div>}
        {!prerequisitesReady && <button className="setup-primary" disabled={busy} onClick={startInstall}>
          {busy ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
          {busy ? t.setupInstalling : t.setupInstall}
        </button>}
        {prerequisitesReady && !status?.model && <button className="setup-primary" disabled={busy} onClick={startModelDownload}>
          {busy ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
          {busy ? t.setupInstalling : t.setupDownloadModel}
        </button>}
        {ready && <button className="setup-primary" onClick={onReady}>{t.setupContinue}</button>}
        <small>{t.setupNote}</small>
      </section>
    </div>
  );
}

function CheckRow({ label, ready, detail }: { label: string; ready: boolean; detail?: string }) {
  return <div className="setup-check"><span className={ready ? "setup-check-icon ready" : "setup-check-icon"}>{ready ? <Check size={14} /> : <CircleAlert size={14} />}</span><strong>{label}</strong><span>{detail}</span></div>;
}
