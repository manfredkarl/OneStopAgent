import { useState, useCallback, useRef } from 'react';
import nikeDemoData from '../data/nike-demo-cache.json';
import type { ChatMessage } from '../types';

const PROCEED_KEYWORDS = new Set(['proceed', 'go', 'yes', 'ok', 'continue', 'start']);

export function useDemoReplay() {
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [isComplete, setIsComplete] = useState(false);

  // Refs for synchronous access — avoids stale-state issues when
  // startDemo() and getNextBatch() are called in the same tick.
  const demoMessagesRef = useRef<ChatMessage[]>([]);
  const currentIndexRef = useRef(0);
  const isDemoRef = useRef(false);

  const startDemo = useCallback(() => {
    const messages: ChatMessage[] = (nikeDemoData as any).messages.map((m: any) => ({
      ...m,
      projectId: m.project_id || m.projectId,
      agentId: m.agent_id || m.agentId,
    }));
    demoMessagesRef.current = messages;
    currentIndexRef.current = 0;
    isDemoRef.current = true;
    setIsDemoMode(true);
    setIsComplete(false);
  }, []);

  /** Return the next batch of *agent* messages up to (and including) the next approval gate. */
  const getNextBatch = useCallback((): ChatMessage[] => {
    if (!isDemoRef.current) return [];

    const batch: ChatMessage[] = [];
    let i = currentIndexRef.current;
    const msgs = demoMessagesRef.current;

    while (i < msgs.length) {
      const msg = msgs[i];

      // Skip user messages — the real user drives those
      if (msg.role === 'user') {
        i++;
        continue;
      }

      batch.push(msg);
      i++;

      // Pause at approval / assumptions gates so the user can click Proceed
      if (msg.metadata?.type === 'approval' || msg.metadata?.type === 'assumptions_input') {
        break;
      }
    }

    currentIndexRef.current = i;
    if (i >= msgs.length) {
      setIsComplete(true);
    }
    return batch;
  }, []);

  /**
   * Process a user message while in demo mode.
   * Returns an array of cached messages to show, or `null` to exit demo and go live.
   */
  const handleDemoMessage = useCallback((message: string): ChatMessage[] | null => {
    if (!isDemoRef.current) return null;

    const trimmed = message.trim();
    const lower = trimmed.toLowerCase();

    // Proceed keywords → replay next batch
    if (PROCEED_KEYWORDS.has(lower)) {
      return getNextBatch();
    }

    // JSON assumptions response (starts with `[{`) → replay next batch
    if (trimmed.startsWith('[{')) {
      return getNextBatch();
    }

    // Anything else → exit demo, go live
    isDemoRef.current = false;
    setIsDemoMode(false);
    return null;
  }, [getNextBatch]);

  const exitDemo = useCallback(() => {
    isDemoRef.current = false;
    setIsDemoMode(false);
  }, []);

  return {
    isDemoMode,
    isComplete,
    startDemo,
    getNextBatch,
    handleDemoMessage,
    exitDemo,
  };
}
