'use client';

import React, { useState, useEffect, useRef } from 'react';

interface RateLimitErrorProps {
  retryAfter: number;
  onDismiss: () => void;
}

export default function RateLimitError({ retryAfter, onDismiss }: RateLimitErrorProps) {
  const [remaining, setRemaining] = useState(retryAfter);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setRemaining(retryAfter);
    intervalRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [retryAfter]);

  useEffect(() => {
    if (remaining === 0) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      onDismiss();
    }
  }, [remaining, onDismiss]);

  return (
    <div
      data-testid="rate-limit-error"
      className="fixed top-4 right-4 z-50 bg-[var(--orange)] text-white px-5 py-3 rounded-lg shadow-lg animate-[fadeIn_0.3s_ease] max-w-sm"
    >
      <div className="flex items-center gap-3">
        <span className="text-lg leading-none">⏳</span>
        <div>
          <p className="text-sm font-semibold">Too many requests</p>
          <p className="text-[13px] opacity-90">
            Retry in{' '}
            <span data-testid="retry-countdown" className="font-bold">
              {remaining}
            </span>{' '}
            seconds.
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="ml-auto text-white/80 hover:text-white text-lg leading-none cursor-pointer bg-transparent border-0"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
