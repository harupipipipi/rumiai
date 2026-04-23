import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { MoreHorizontal, Play, Edit2, Copy, Trash2, Star, Box, AlertCircle, Rocket } from 'lucide-react';
import { Card } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import { Button } from '@/src/components/ui/Button';
import { Popover, PopoverTrigger, PopoverContent } from '@/src/components/ui/Popover';
import type { StartupProfileView } from '@/src/lib/startupProfiles';
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
  const { profile, standardPack, runtimeReady, issues, lastLaunched } = profileView;

  const hasDanger = issues.some((i) => i.severity === 'danger');
  const hasWarning = issues.some((i) => i.severity === 'warning');

  return (
    <Card className={cn(
      "group relative overflow-hidden transition-all duration-300 hover:border-accent/40 hover:shadow-md",
      isActive && "border-accent/50 ring-1 ring-accent/20"
    )}>
      {/* Active Indicator (Subtle) */}
      {isActive && (
        <div className="absolute top-0 right-0 p-3">
          <div className="h-2 w-2 rounded-full bg-accent animate-pulse shadow-[0_0_8px_rgba(99,102,241,0.6)]" />
        </div>
      )}

      <div className="p-5">
        <div className="flex items-start justify-between">
          <div className="flex-1 space-y-1">
            <h3 className="font-semibold text-text-main line-clamp-1">{profile.name}</h3>
            <p className="text-xs text-text-muted flex items-center gap-1">
              <Box className="h-3 w-3" />
              {standardPack?.display_name || 'No Standard Pack'}
            </p>
          </div>

          <Popover>
            <PopoverTrigger className="rounded-md p-1 hover:bg-bg-hover text-text-muted transition-colors">
              <MoreHorizontal className="h-4 w-4" />
            </PopoverTrigger>
            <PopoverContent className="w-40" align="right">
              <div className="flex flex-col">
                <button
                  onClick={() => onEdit(profile.profile_id)}
                  className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-bg-hover transition-colors rounded-md text-left"
                >
                  <Edit2 className="h-3.5 w-3.5" /> Edit
                </button>
                <button
                  onClick={() => onActivate(profile.profile_id)}
                  disabled={isActive}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-sm hover:bg-bg-hover transition-colors rounded-md text-left",
                    isActive && "opacity-50 cursor-not-allowed"
                  )}
                >
                  <Star className={cn("h-3.5 w-3.5", isActive && "fill-accent text-accent")} /> 
                  {isActive ? "Active" : "Set Active"}
                </button>
                <button
                  onClick={() => onDuplicate(profile.profile_id)}
                  className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-bg-hover transition-colors rounded-md text-left"
                >
                  <Copy className="h-3.5 w-3.5" /> Duplicate
                </button>
                <div className="my-1 border-t border-border" />
                <button
                  onClick={() => onDelete(profile.profile_id, profile.name)}
                  className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-rose-500/10 text-rose-500 transition-colors rounded-md text-left"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
              </div>
            </PopoverContent>
          </Popover>
        </div>

        {/* Status Area */}
        <div className="mt-4 min-h-[40px]">
          {issues.length > 0 ? (
            <div className={cn(
              "flex items-start gap-2 rounded-lg p-2 text-xs",
              hasDanger ? "bg-rose-500/10 text-rose-500" : "bg-amber-500/10 text-amber-500"
            )}>
              <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span className="line-clamp-2">{issues[0].description}</span>
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {lastLaunched && <Badge variant="secondary" className="text-[10px] py-0 h-5">Last Used</Badge>}
              <Badge variant="outline" className="text-[10px] py-0 h-5 border-emerald-500/30 text-emerald-500 bg-emerald-500/5">
                Ready
              </Badge>
            </div>
          )}
        </div>

        {/* Primary Action */}
        <div className="mt-5">
          <Button
            onClick={() => onLaunch(profile.profile_id)}
            disabled={!runtimeReady || isBusy}
            size="sm"
            className={cn(
              "w-full h-9 gap-2 font-medium transition-all duration-300",
              runtimeReady 
                ? "bg-accent hover:bg-accent/90 text-accent-fg shadow-sm hover:shadow-accent/20" 
                : "bg-bg-hover text-text-muted border-dashed border-border"
            )}
          >
            {isBusy && actionType === 'launch' ? (
              <div className="h-3 w-3 border-2 border-accent-fg/30 border-t-accent-fg rounded-full animate-spin" />
            ) : (
              <Rocket className="h-3.5 w-3.5" />
            )}
            Launch
          </Button>
        </div>
      </div>
    </Card>
  );
}
