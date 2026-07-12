import { HistoryBoard } from "../components/HistoryBoard";
import type { HistoryBoardRendererProps } from "./types";

export function HistoryBoardRenderer(props: HistoryBoardRendererProps) {
  return <HistoryBoard {...props} />;
}
