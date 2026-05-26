import {Play, Rocket, Save, Sparkles} from 'lucide-react';

import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {PROFILE_GRAPH_CATEGORY_LABELS, type ProfileGraphCategory} from '@/src/lib/profileGraph';

interface ProfileGraphToolbarProps {
  activeCategory: ProfileGraphCategory;
  dirty: boolean;
  saving?: boolean;
  previewing?: boolean;
  launching?: boolean;
  onCategoryChange: (category: ProfileGraphCategory) => void;
  onPreview: () => void;
  onApply: () => void;
  onLaunch: () => void;
}

export function ProfileGraphToolbar({
  activeCategory,
  dirty,
  saving,
  previewing,
  launching,
  onCategoryChange,
  onPreview,
  onApply,
  onLaunch,
}: ProfileGraphToolbarProps) {
  return (
    <section className="rounded-2xl border border-border bg-bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="default">
            <Sparkles className="h-3.5 w-3.5" />
            Design
          </Badge>
          {(Object.keys(PROFILE_GRAPH_CATEGORY_LABELS) as ProfileGraphCategory[]).map((category) => (
            <Button
              key={category}
              type="button"
              size="sm"
              variant={category === activeCategory ? 'default' : 'outline'}
              onClick={() => onCategoryChange(category)}
            >
              {PROFILE_GRAPH_CATEGORY_LABELS[category]}
            </Button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {dirty ? <Badge variant="secondary">Unsaved</Badge> : <Badge variant="outline">Synced</Badge>}
          <Button type="button" size="sm" variant="outline" loading={previewing} onClick={onPreview}>
            <Play className="h-4 w-4" />
            Preview Runtime
          </Button>
          <Button type="button" size="sm" loading={saving} onClick={onApply}>
            <Save className="h-4 w-4" />
            Apply
          </Button>
          <Button type="button" size="sm" variant="secondary" loading={launching} onClick={onLaunch}>
            <Rocket className="h-4 w-4" />
            Launch
          </Button>
        </div>
      </div>
    </section>
  );
}
