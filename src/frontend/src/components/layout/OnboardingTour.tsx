import { useState, useEffect, useCallback, useRef } from 'react';

interface TourStep {
  targetSelector: string;
  title: string;
  description: string;
  position: 'top' | 'bottom' | 'left' | 'right';
}

const TOUR_STEPS: TourStep[] = [
  {
    targetSelector: '[data-tour="agents"]',
    title: '🤖 Your AI Agents',
    description:
      'These are your specialized Azure agents. Toggle them on/off to customize your pipeline. Each agent handles a different aspect — architecture, cost, business value, ROI, and presentation.',
    position: 'right',
  },
  {
    targetSelector: '[data-tour="company-search"]',
    title: '🔍 Company Intelligence',
    description:
      'Search for any company to enrich your proposal with real data — employee count, revenue, industry, and Azure usage. This context flows into every agent\'s analysis.',
    position: 'bottom',
  },
  {
    targetSelector: '[data-tour="description"]',
    title: '📝 Describe Your Project',
    description:
      'Describe the Azure solution you want to build. Be specific about use cases, scale, and requirements. Our AI agents will design the architecture, estimate costs, calculate ROI, and generate a presentation.',
    position: 'bottom',
  },
  {
    targetSelector: '[data-tour="msx-opportunities"]',
    title: '🎯 Your Opportunities',
    description:
      'Pull your active opportunities from MSX. Click one to auto-fill the project description with the opportunity details — ready for your agents to analyze.',
    position: 'top',
  },
  {
    targetSelector: '[data-tour="industry-templates"]',
    title: '💡 Industry Templates',
    description:
      'Pre-built scenarios across industries. Click any to start with a detailed use case — from AI-powered relationship managers to agentic commerce platforms.',
    position: 'top',
  },
];

const STORAGE_KEY = 'onboarding_completed';

export default function OnboardingTour() {
  const [active, setActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [transitioning, setTransitioning] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Always show onboarding on page load (for demo purposes)
  useEffect(() => {
    const timer = setTimeout(() => setActive(true), 600);
    return () => clearTimeout(timer);
  }, []);

  const finish = useCallback(() => {
    setActive(false);
  }, []);

  // Locate target element and update rect
  const updateRect = useCallback(() => {
    const step = TOUR_STEPS[currentStep];
    const el = document.querySelector(step.targetSelector);
    if (el) {
      setRect(el.getBoundingClientRect());
    }
  }, [currentStep]);

  // On step change: scroll into view then measure
  useEffect(() => {
    if (!active) return;

    const step = TOUR_STEPS[currentStep];
    const el = document.querySelector(step.targetSelector);
    if (!el) {
      updateRect();
      return;
    }

    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const timer = setTimeout(() => {
      updateRect();
      setTransitioning(false);
    }, 400);

    return () => clearTimeout(timer);
  }, [active, currentStep, updateRect]);

  // Resize handler
  useEffect(() => {
    if (!active) return;
    const handle = () => updateRect();
    window.addEventListener('resize', handle);
    return () => window.removeEventListener('resize', handle);
  }, [active, updateRect]);

  const goNext = () => {
    if (currentStep < TOUR_STEPS.length - 1) {
      setTransitioning(true);
      setCurrentStep(s => s + 1);
    } else {
      finish();
    }
  };

  const goPrev = () => {
    if (currentStep > 0) {
      setTransitioning(true);
      setCurrentStep(s => s - 1);
    }
  };

  if (!active) return null;

  const step = TOUR_STEPS[currentStep];
  const isLast = currentStep === TOUR_STEPS.length - 1;

  // Spotlight style
  const spotlightStyle: React.CSSProperties = rect
    ? {
        position: 'fixed',
        top: rect.top - 8,
        left: rect.left - 8,
        width: rect.width + 16,
        height: rect.height + 16,
        borderRadius: 12,
        boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.65)',
        zIndex: 1000,
        pointerEvents: 'none',
        transition: 'top 0.35s ease, left 0.35s ease, width 0.35s ease, height 0.35s ease',
      }
    : { display: 'none' };

  // Tooltip positioning
  const tooltipStyle: React.CSSProperties = (() => {
    if (!rect) return { display: 'none' };

    const gap = 16;
    const base: React.CSSProperties = {
      position: 'fixed',
      zIndex: 1001,
      maxWidth: 370,
      transition: 'top 0.35s ease, left 0.35s ease, opacity 0.25s ease',
      opacity: transitioning ? 0 : 1,
    };

    switch (step.position) {
      case 'right':
        return { ...base, left: rect.right + gap, top: rect.top };
      case 'left':
        return { ...base, left: rect.left - 370 - gap, top: rect.top };
      case 'bottom':
        return { ...base, left: rect.left, top: rect.bottom + gap };
      case 'top':
        return { ...base, left: rect.left, top: rect.top - gap };
      default:
        return base;
    }
  })();

  // For 'top' position, use transform to anchor bottom edge to the computed top
  if (step.position === 'top' && rect) {
    tooltipStyle.transform = 'translateY(-100%)';
  }

  return (
    <>
      {/* Clickable overlay behind spotlight — clicking it does nothing (prevents interaction) */}
      <div
        style={{ position: 'fixed', inset: 0, zIndex: 999 }}
        onClick={e => e.stopPropagation()}
      />

      {/* Spotlight cutout */}
      <div style={spotlightStyle} />

      {/* Tooltip card */}
      <div ref={tooltipRef} style={tooltipStyle}>
        <div
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            borderRadius: 14,
            padding: '20px 22px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.45)',
          }}
        >
          {/* Title */}
          <p
            style={{
              color: 'var(--accent)',
              fontWeight: 700,
              fontSize: 16,
              marginBottom: 8,
            }}
          >
            {step.title}
          </p>

          {/* Description */}
          <p
            style={{
              color: 'var(--text-secondary)',
              fontSize: 13,
              lineHeight: 1.55,
              marginBottom: 18,
            }}
          >
            {step.description}
          </p>

          {/* Step indicator */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span
              style={{
                fontSize: 12,
                color: 'var(--text-muted)',
              }}
            >
              {currentStep + 1} of {TOUR_STEPS.length}
            </span>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {/* Skip */}
              <button
                onClick={finish}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  fontSize: 12,
                  cursor: 'pointer',
                  padding: '4px 8px',
                }}
              >
                Skip tour
              </button>

              {/* Back */}
              {currentStep > 0 && (
                <button
                  onClick={goPrev}
                  style={{
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border-light)',
                    color: 'var(--text-secondary)',
                    fontSize: 13,
                    fontWeight: 500,
                    padding: '6px 14px',
                    borderRadius: 8,
                    cursor: 'pointer',
                  }}
                >
                  Back
                </button>
              )}

              {/* Next / Get Started */}
              <button
                onClick={goNext}
                style={{
                  background: 'var(--accent)',
                  border: 'none',
                  color: '#fff',
                  fontSize: 13,
                  fontWeight: 600,
                  padding: '6px 18px',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                {isLast ? 'Get Started' : 'Next'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
