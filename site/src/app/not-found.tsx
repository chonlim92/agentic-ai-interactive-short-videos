import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center px-6">
      <h1 className="text-6xl font-black tracking-tight mb-4">
        <span className="glow-text">404</span>
      </h1>
      <p className="text-white/40 text-lg mb-8">Page not found</p>
      <Link
        href="/"
        className="btn-primary px-6 py-3 text-sm"
      >
        Go Home
      </Link>
    </div>
  );
}
