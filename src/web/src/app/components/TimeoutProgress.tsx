'use client';

import React, { useState, useEffect, useRef } from 'react';

interface TimeoutProgressProps {
  softTimeout: number;
  hardTimeout: number;
  isActive: boolean;
}

export default function TimeoutProgress({ softTimeout, hardTimeout, isActive }: TimeoutProgressProps) {
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isActive) {
      setElapsed(0);
      intervalRef.current = setInterval(() => {
        setElapsed((prev) => prev + 1);
      }, 1000);
    } else {
      setElapsed(0);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isActive]);

  if (!isActive) return null;

  const pastSoftTimeout = elapsed >= softTimeout;
  const progress = pastSoftTimeout
    ? 50 + Math.min(((elapsed - softTimeout) / (hardTimeout - softTimeout)) * 50, 50)
    : Math.min((elapsed / softTimeout) * 50, 50);
  const barColor = pastSoftTimeout ? 'var(--orange)' : 'var(--accent)';

  return (
    <div data-testid="timeout-progress" className="w-full">
      {/* Progress bar */}
      <div className="w-full h-1 bg-[var(--border)] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${progress}%`,
            backgroundColor: barColor,
            transition: 'width 1s linear, background-color 0.3s ease',
          }}
        />
      </div>

      {/* Status text */}
      <div className="flex items-center justify-between mt-1">
        <span className="text-[11px] text-[var(--text-secondary)]">
          Generating... ({elapsed}s)
        </span>
        {pastSoftTimeout && (
          <span
            data-testid="timeout-warning"
            className="text-[11px] text-[var(--orange)] font-medium"
          >
            Taking longer than expected...
          </span>
        )}
      </div>
    </div>
  );
}
