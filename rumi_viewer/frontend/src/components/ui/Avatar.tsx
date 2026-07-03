import { useState } from 'react';
import { profileInitial } from '@/src/lib/avatar';
import { cn } from '@/src/lib/utils';

type AvatarProps = {
  src?: string | null;
  username: string;
  className?: string;
  imageClassName?: string;
  alt?: string;
};

export function Avatar({ src, username, className, imageClassName, alt = '' }: AvatarProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = Boolean(src) && !imageFailed;

  return showImage ? (
    <img
      src={src || undefined}
      alt={alt}
      className={cn('rounded-full border border-border object-cover', className, imageClassName)}
      referrerPolicy="no-referrer"
      onError={() => setImageFailed(true)}
    />
  ) : (
    <div
      className={cn('flex rounded-full border border-border bg-accent/20 items-center justify-center text-accent font-semibold', className)}
      aria-label={alt || undefined}
      role={alt ? 'img' : undefined}
    >
      {profileInitial(username)}
    </div>
  );
}
