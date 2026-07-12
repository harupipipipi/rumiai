import { TitleBar } from "../components/TitleBar";
import type { TitleBarRendererProps } from "./types";

export function TitleBarRenderer(props: TitleBarRendererProps) {
  return <TitleBar appName={props.appName} appIcon={props.appIcon} />;
}
