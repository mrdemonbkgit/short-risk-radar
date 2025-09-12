import "./globals.css";

if (typeof window !== "undefined") {
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (dsn) {
    import("@sentry/browser").then((Sentry) => {
      Sentry.init({ dsn, tracesSampleRate: 0.1, environment: process.env.NODE_ENV });
    });
  }
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100">
        {children}
      </body>
    </html>
  );
}
