import { Check, Pencil, ShieldCheck, X } from "lucide-react";

import type { PendingToolReview } from "./types";

export function ToolSelectionReviewCard({
  review,
  labelForService,
  onApprove,
  onEdit,
  onNoTools,
  onCancel,
}: {
  review: PendingToolReview;
  labelForService: (serviceId: string) => string;
  onApprove: () => void;
  onEdit: () => void;
  onNoTools: () => void;
  onCancel: () => void;
}) {
  const services = review.decision.selected_services ?? [];
  const recommendations = review.decision.recommendations ?? [];
  const permissionSummary = review.decision.permission_summary ?? {};
  const confirmCount = Number(permissionSummary.confirm ?? 0);
  const autoCount = Number(permissionSummary.auto ?? 0);
  const title = services.length
    ? services.map((service) => labelForService(service.service_id)).slice(0, 3).join("、")
    : "機能なし";

  return (
    <section
      aria-live="polite"
      className="mx-4 mb-2 rounded-2xl border border-zinc-800 bg-zinc-950/95 p-3 shadow-2xl max-[640px]:mx-2"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-zinc-700 bg-zinc-900 text-zinc-200">
          <ShieldCheck size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-zinc-100">使用する機能を確認</p>
              <p className="mt-0.5 text-xs text-zinc-500">{title}</p>
            </div>
            <button
              type="button"
              aria-label="機能確認をキャンセル"
              onClick={onCancel}
              className="rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-900 hover:text-zinc-100"
            >
              <X size={15} />
            </button>
          </div>

          <div className="mt-3 grid gap-2">
            {services.length === 0 && (
              <p className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-xs text-zinc-400">
                この入力では追加の機能は必要なさそうです
              </p>
            )}
            {services.map((service) => {
              const recommendation = recommendations.find((item) => service.service_id && item.tool_id?.includes(service.service_id));
              return (
                <div key={service.service_id} className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-[13px] font-medium text-zinc-100">{labelForService(service.service_id)}</p>
                    <span className="flex-shrink-0 text-[11px] text-zinc-500">{service.tool_count ?? 0}件</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-zinc-500">
                    {recommendation?.reason || service.summary || "依頼内容に必要な機能です"}
                  </p>
                </div>
              );
            })}
          </div>

          <p className="mt-3 text-[11px] leading-relaxed text-zinc-500">
            機能を選ぶ確認と、変更・送信操作の承認は別です。変更を伴う操作は実行直前にもう一度確認されます。
          </p>
          <p className="mt-1 text-[11px] text-zinc-600">
            自動 {autoCount}件・実行前に確認 {confirmCount}件
          </p>

          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-zinc-700 px-3 text-xs text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
            >
              <Pencil size={13} />
              機能を編集
            </button>
            <button
              type="button"
              onClick={onNoTools}
              className="h-9 rounded-xl border border-zinc-700 px-3 text-xs text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
            >
              機能なしで続ける
            </button>
            <button
              type="button"
              onClick={onApprove}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-zinc-100 px-3 text-xs font-semibold text-zinc-950 hover:bg-white"
            >
              <Check size={13} />
              この内容で続ける
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
