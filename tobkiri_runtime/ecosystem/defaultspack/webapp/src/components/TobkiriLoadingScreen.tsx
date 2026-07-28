const assetBaseUrl = (
  import.meta as ImportMeta & { env?: { BASE_URL?: string } }
).env?.BASE_URL || "/static/";

export const TOBKIRI_LOADING_ANIMATION_URL =
  `${assetBaseUrl}assets/tobkiri-startup-blade-cut.svg`;

export const TOBKIRI_LOADING_LABEL = "Tobkiriを読み込んでいます…";

/**
 * Brand-aligned startup state shared by the shell bootstrap boundaries.
 *
 * The animated SVG is the same local asset used by Tobkiri Launcher. People
 * who prefer reduced motion see a stable wordmark instead of the animation.
 */
export function TobkiriLoadingScreen() {
  return (
    <main
      aria-label={TOBKIRI_LOADING_LABEL}
      aria-live="polite"
      className="flex h-full min-h-screen w-full items-center justify-center overflow-hidden bg-[#09090b] px-6 py-12 text-zinc-100"
      data-tobkiri-loading-screen=""
      role="status"
    >
      <div
        aria-hidden="true"
        className="flex w-full max-w-xl flex-col items-center gap-4 text-center"
      >
        <img
          alt=""
          className="aspect-[2/1] w-full object-contain mix-blend-screen invert motion-reduce:hidden"
          data-loading-scene="launcher"
          src={TOBKIRI_LOADING_ANIMATION_URL}
        />
        <div
          className="hidden aspect-[2/1] w-full items-center justify-center motion-reduce:flex"
          data-reduced-motion-wordmark=""
        >
          <span className="text-4xl font-semibold tracking-tight text-zinc-50">
            Tobkiri
          </span>
        </div>
        <p className="text-base font-semibold tracking-tight text-zinc-100">
          Tobkiri
        </p>
        <p className="text-sm text-zinc-400">{TOBKIRI_LOADING_LABEL}</p>
      </div>
    </main>
  );
}
