'use client';

import React, { useState, useCallback } from 'react';
import type { GuidedQuestion } from '@/types';

interface GuidedQuestionsProps {
  question: GuidedQuestion;
  questionNumber: number;
  totalQuestions: number;
  onAnswer: (answer: string) => void;
  onSkip: () => void;
  onProceed: () => void;
}

const CATEGORY_DISPLAY: Record<string, string> = {
  users: 'Users',
  scale: 'Scale',
  geography: 'Geography',
  compliance: 'Compliance',
  integration: 'Integration',
  timeline: 'Timeline',
  value: 'Value',
};

export default function GuidedQuestions({
  question,
  questionNumber,
  totalQuestions,
  onAnswer,
  onSkip,
  onProceed,
}: GuidedQuestionsProps) {
  const [inputValue, setInputValue] = useState('');

  const handleSubmit = useCallback(() => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    onAnswer(trimmed);
    setInputValue('');
  }, [inputValue, onAnswer]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const progress = totalQuestions > 0 ? (questionNumber / totalQuestions) * 100 : 0;

  return (
    <div data-testid="guided-questions" className="space-y-4">
      {/* Progress */}
      <div className="flex items-center justify-between text-xs text-[var(--text-secondary)]">
        <span data-testid="question-progress">
          Question {questionNumber} of {totalQuestions}
        </span>
        <span
          data-testid="question-category"
          className="bg-[var(--bg-secondary)] text-[var(--text-secondary)] px-2 py-0.5 rounded-full text-[11px] font-medium uppercase tracking-wide"
        >
          {CATEGORY_DISPLAY[question.category] ?? question.category}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1.5 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
        <div
          data-testid="progress-bar"
          className="h-full bg-[var(--accent)] rounded-full transition-all duration-300"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Question */}
      <p data-testid="question-text" className="text-sm font-medium text-[var(--text-primary)] leading-relaxed">
        {question.questionText}
      </p>

      {/* Default hint */}
      {question.defaultValue && (
        <p data-testid="default-hint" className="text-xs text-[var(--text-muted)] italic">
          Default: {question.defaultValue}
        </p>
      )}

      {/* Input */}
      <input
        data-testid="question-input"
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type your answer..."
        className="w-full px-3.5 py-2.5 border border-[var(--disabled-bg)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)] focus:shadow-[0_0_0_1px_var(--accent)] transition-colors"
      />

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button
          data-testid="answer-button"
          type="button"
          disabled={inputValue.trim().length === 0}
          onClick={handleSubmit}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
            inputValue.trim().length > 0
              ? 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] cursor-pointer'
              : 'bg-[var(--bg-secondary)] text-[var(--text-muted)] cursor-not-allowed'
          }`}
        >
          Answer
        </button>

        <button
          data-testid="skip-button"
          type="button"
          onClick={onSkip}
          className="px-4 py-2 rounded-lg text-sm font-medium text-[var(--text-secondary)] bg-[var(--bg-secondary)] hover:bg-[var(--border)] transition-colors cursor-pointer"
        >
          ⚠️ Skip (use default)
        </button>

        <div className="flex-1" />

        <button
          data-testid="start-agents-button"
          type="button"
          onClick={onProceed}
          className="px-4 py-2 rounded-lg text-sm font-medium border border-[var(--disabled-bg)] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors cursor-pointer"
        >
          Start Agents →
        </button>
      </div>
    </div>
  );
}
