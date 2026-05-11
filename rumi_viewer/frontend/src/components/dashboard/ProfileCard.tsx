import { MoreHorizontal, Rocket, Edit2, Copy, Trash2, Star, Box, AlertCircle } from 'lucide-react';
import { Card } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Button } from '@/src/components/ui/Button';
import { Popover, PopoverTrigger, PopoverContent } from '@/src/components/ui/Popover';
import { packLabel, type StartupProfileView } from '@/src/lib/startupProfiles';
import { cn } from '@/src/lib/utils';

interface ProfileCardProps {
  profileView: StartupProfileView;
  isActive: boolean;
  onLaunch: (id: string) => void;
  onEdit: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string, name: string) => void;
  onActivate: (id: string) => void;
  isBusy: boolean;
  actionType?: string | null;
}

export function ProfileCard({
  profileView,
  isActive,
  onLaunch,
  onEdit,
  onDuplicate,
  onDelete,
  onActivate,
  isBusy,
  actionType,
}: ProfileCardProps) {
  const { profile, basePack, runtimeReady, issues, lastLaunched } = profileView;
  const hasDanger = issues.some((i) => i.severity === 'danger');

  return (
    <Card className={cn(
      "group relative flex flex-col overflow-hidden transition-all duration-[var(--transition-base)] hover:shadow-[var(--shadow-md)]",
      isActive && "ring-1 ring-accent/30"
    )}>
      <div className="p-5 flex flex-col flex-1">
        {/* Header: name + menu */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-text-main truncate">{profile.name}</h3>
              {isActive && (
                <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_6px_var(--accent)]" aria-label="Active profile" />
              )}
            </div>
            <p className="mt-1 text-xs text-text-muted flex items-center gap-1.5 truncate">
              <Box className="h-3 w-3 shrink-0" />
              {packLabel(basePack, profile.base_pack)}
            </p>
          </div>

          <Popover>
            <PopoverTrigger className="rounded-md p-1.5 hover:bg-bg-hover text-text-muted transition-colors opacity-0 group-hover:opacity-100 focus-visible:opacity-100">
              <MoreHorizontal className="h-4 w-4" />
              <span className="sr-only">Profile actions</span>
            </PopoverTrigger>
            <PopoverContent className="w-40" align="right">
              <div className="flex flex-col py-1">
                <button
                  onClick={() => onEdit(profile.profile_id)}
                  className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-bg-hover transition-colors rounded-md text-left text-text-main"
                >
                  <Edit2 className="h-3.5 w-3.5" /> Edit
                </button>
                <button
                  onClick={() => onActivate(profile.profile_id)}
                  disabled={isActive}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-sm hover:bg-bg-hover transition-colors rounded-md text-left",
                    isActive ? "opacity-50 cursor-not-allowed text-text-muted" : "text-text-main"
                  )}
                >
                  <Star className={cn("h-3.5 w-3.5", isActive && "fill-accent text-accent")} />
                  {isActive ? "Active" : "Set Active"}
                </button>
                <button
                  onClick={() => onDuplicate(profile.profile_id)}
                  className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-bg-hover transition-colors rounded-md text-left text-text-main"
                >
                  <Copy className="h-3.5 w-3.5" /> Duplicate
                </button>
                <div className="my-1 border-t border-border" />
                <button
                  onClick={() => onDelete(profile.profile_id, profile.name)}
                  className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-red-50 dark:hover:bg-red-950/20 text-red-500 transition-colors rounded-md text-left"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
              </div>
            </PopoverContent>
          </Popover>
        </div>

        {/* Status */}
        <div className="mt-4 min-h-[32px]">
          {issues.length > 0 ? (
            <div className={cn(
              "flex items-start gap-2 rounded-lg p-2.5 text-xs",
              hasDanger ? "bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400" : "bg-amber-50 text-amber-600 dark:bg-amber-950/20 dark:text-amber-400"
            )}>
              <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span className="line-clamp-2">{issues[0].description}</span>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {isActive && <Badge variant="default" className="text-[10px]">Active</Badge>}
              {lastLaunched && <Badge variant="secondary" className="text-[10px]">Last Used</Badge>}
              <Badge variant="success" className="text-[10px]">Ready</Badge>
            </div>
          )}
        </div>

        {/* Primary action - bottom right aligned */}
        <div className="mt-auto pt-4 flex justify-end">
          <Button
            onClick={() => onLaunch(profile.profile_id)}
            disabled={!runtimeReady || isBusy}
            size="sm"
            loading={isBusy && actionType === 'launch'}
            aria-label={`Launch ${profile.name}`}
          >
            <Rocket className="h-3.5 w-3.5" />
            Launch
          </Button>
        </div>
      </div>
    </Card>
  );
}
