/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef } from 'react';

/**
 * Returns a ref that tracks whether the component is currently mounted.
 * Useful for guarding async operations against unmounted state updates.
 */
export function useMountedRef() {
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return mountedRef;
}
