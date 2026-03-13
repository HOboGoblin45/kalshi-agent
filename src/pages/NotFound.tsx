import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="h-full min-h-[60vh] flex items-center justify-center p-4">
      <div className="card max-w-sm w-full text-center">
        <p className="text-[11px] text-text-tertiary mb-1">404</p>
        <h1 className="text-lg font-bold mb-2">Page Not Found</h1>
        <p className="text-xs text-text-secondary mb-3">
          The page you requested does not exist or has moved.
        </p>
        <Link
          to="/"
          className="inline-flex items-center justify-center h-8 px-3 rounded-md text-xs font-semibold text-white"
          style={{ background: "var(--accent-color)" }}
        >
          Back to Markets
        </Link>
      </div>
    </div>
  );
}
