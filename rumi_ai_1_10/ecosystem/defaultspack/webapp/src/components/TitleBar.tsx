import { useState, useEffect } from 'react';
import { Minus, Square, X, Copy } from 'lucide-react';

let tauriWindow: any = null;
let tauriReady = false;

// 起動時に一度だけ読み込み
async function initTauri() {
  if (tauriReady) return tauriWindow;
  try {
    const mod = await import('@tauri-apps/api/window');
    tauriWindow = mod.getCurrentWindow();
    tauriReady = true;
    return tauriWindow;
  } catch {
    tauriReady = true;
    return null;
  }
}

type TitleBarProps = {
  appName?: string;
  appIcon?: string;
};

export function TitleBar({ appName = "Console", appIcon }: TitleBarProps) {
  const [isMaximized, setIsMaximized] = useState(false);
  const [isTauri, setIsTauri] = useState(false);

  useEffect(() => {
    initTauri().then(win => {
      if (win) {
        setIsTauri(true);
        win.isMaximized().then((m: boolean) => setIsMaximized(m));
      }
    });
  }, []);

  const handleMinimize = async () => {
    const win = await initTauri();
    await win?.minimize();
  };

  const handleMaximize = async () => {
    const win = await initTauri();
    if (!win) return;
    const maximized = await win.isMaximized();
    if (maximized) {
      await win.unmaximize();
      setIsMaximized(false);
    } else {
      await win.maximize();
      setIsMaximized(true);
    }
  };

  const handleClose = async () => {
    const win = await initTauri();
    await win?.close();
  };

  const handleDrag = async (e: React.MouseEvent) => {
    // ボタン上ではドラッグしない
    if ((e.target as HTMLElement).closest('button')) return;
    const win = await initTauri();
    await win?.startDragging();
  };

  const handleDoubleClick = async () => {
    await handleMaximize();
  };

  return (
    <div
      onMouseDown={handleDrag}
      onDoubleClick={handleDoubleClick}
      className="rumi-ambient h-8 flex items-center justify-between bg-[#09090b] border-b border-zinc-800/60 select-none flex-shrink-0 cursor-default"
    >
      {/* Left: App icon + name */}
      <div className="flex items-center gap-2 px-3 flex-1 pointer-events-none">
        {appIcon ? (
          <img src={appIcon} alt="" className="w-4 h-4 rounded object-cover flex-shrink-0" />
        ) : (
          <div className="w-4 h-4 rounded bg-zinc-800 border border-zinc-700/80 flex items-center justify-center flex-shrink-0">
            <span className="text-[9px] font-mono font-bold text-zinc-300">&gt;</span>
          </div>
        )}
        <span className="text-[11px] font-medium text-zinc-500">
          {appName}
        </span>
      </div>

      {/* Right: Window controls */}
      {isTauri && (
        <div className="flex items-center h-full">
          <button
            onClick={handleMinimize}
            aria-label="Minimize window"
            className="rumi-luxe-tap h-full px-3 flex items-center justify-center text-zinc-500 hover:bg-zinc-800/70 hover:text-zinc-300 transition-colors"
          >
            <Minus size={12} />
          </button>
          <button
            onClick={handleMaximize}
            aria-label={isMaximized ? "Restore window" : "Maximize window"}
            className="rumi-luxe-tap h-full px-3 flex items-center justify-center text-zinc-500 hover:bg-zinc-800/70 hover:text-zinc-300 transition-colors"
          >
            {isMaximized ? <Copy size={10} /> : <Square size={10} />}
          </button>
          <button
            onClick={handleClose}
            aria-label="Close window"
            className="rumi-luxe-tap h-full px-3 flex items-center justify-center text-zinc-500 hover:bg-red-600 hover:text-white transition-colors"
          >
            <X size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
