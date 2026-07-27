export type TaskPetMood = "idle" | "thinking" | "completed" | "error";

export type TaskPetViewModel = {
  detail: string;
  label: string;
  mood: TaskPetMood;
  title: string;
};

export const TASK_PET_DETAIL_TEXT_LIMIT = 118;
const TASK_TEXT_LIMIT = 92;

export function truncateTaskPetText(value: string | null | undefined, limit: number): string {
  const normalized = String(value ?? "").replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, Math.max(1, limit - 1)).trimEnd()}…`;
}

export function taskPetViewModel(
  mood: TaskPetMood,
  taskText?: string | null,
  activityText?: string | null,
  error?: string | null,
): TaskPetViewModel {
  const task = truncateTaskPetText(taskText, TASK_TEXT_LIMIT);
  const activity = truncateTaskPetText(activityText, TASK_PET_DETAIL_TEXT_LIMIT);

  if (mood === "thinking") {
    return {
      mood,
      label: "思考中",
      title: task || "タスクを進めています",
      detail: activity || "必要な手順をひとつずつ確認しています。",
    };
  }
  if (mood === "completed") {
    return {
      mood,
      label: "完了",
      title: "できたよ！",
      detail: task ? `${task} を完了しました。` : "タスクが完了しました。",
    };
  }
  if (mood === "error") {
    return {
      mood,
      label: "要確認",
      title: "途中で止まりました",
      detail: truncateTaskPetText(error, TASK_PET_DETAIL_TEXT_LIMIT) || "画面のエラーを確認してください。",
    };
  }
  return {
    mood,
    label: "Tobkiri ペット",
    title: "ここで見守っています",
    detail: "タスクを始めると、進み具合をここに表示します。",
  };
}

export function shouldSendDesktopNotification(
  permission: NotificationPermission,
  visibilityState: DocumentVisibilityState,
): boolean {
  return permission === "granted" && visibilityState === "hidden";
}
