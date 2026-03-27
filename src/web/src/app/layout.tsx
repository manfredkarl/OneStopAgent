import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import ClientProviders from "./components/ClientProviders";

export const metadata: Metadata = {
  title: "OneStopAgent",
  description: "Scope Azure solutions in minutes with AI agents.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: `
          // Remove Next.js route announcer custom element to prevent aria-live conflicts
          (function() {
            function fix() {
              var els = document.getElementsByTagName('next-route-announcer');
              for (var i = els.length - 1; i >= 0; i--) els[i].remove();
            }
            setInterval(fix, 100);
            if (typeof MutationObserver !== 'undefined') {
              new MutationObserver(fix).observe(document.documentElement, { childList: true, subtree: true });
            }
          })();
        `}} />
      </head>
      <body className="antialiased">
        {/* Skip to content */}
        <a href="#main-content" className="skip-to-content">
          Skip to content
        </a>

        {/* Top bar — minimal Copilot style */}
        <nav className="h-12 bg-[var(--bg-primary)] border-b border-[var(--border-subtle)] flex items-center px-4 sm:px-5 shrink-0 z-10" role="navigation" aria-label="Main navigation">
          <Link href="/" className="flex items-center gap-2.5 text-[var(--text-primary)] no-underline font-semibold text-[14px] hover:opacity-80 transition-opacity">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/onestopagent-logo.svg" alt="" width={24} height={24} className="rounded-md" aria-hidden="true" />
            <span className="tracking-[-0.01em]">OneStopAgent</span>
          </Link>

          <div className="flex-1" />

          <Link href="/projects" className="text-[var(--text-secondary)] text-[13px] font-medium hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] no-underline px-3 py-1.5 rounded-md transition-colors hidden sm:inline-block mr-2">
            Projects
          </Link>

          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--accent)] to-[var(--accent-hover)] flex items-center justify-center text-[12px] font-semibold text-white cursor-pointer hover:opacity-90 transition-opacity shadow-[var(--shadow-sm)]" aria-label="User menu">
            U
          </div>
        </nav>

        <div id="main-content" className="flex flex-col" style={{ height: 'calc(100vh - 48px)' }}>
          <ClientProviders>
            {children}
          </ClientProviders>
        </div>
      </body>
    </html>
  );
}
