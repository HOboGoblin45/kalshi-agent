import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="h-full min-h-[60vh] flex items-center justify-center p-4">
      <div className="card max-w-sm w-full text-center py-8">
        <pre className="text-accent-red text-xs term-glow mb-3">
{`  _  _    ___  _  _
 | || |  / _ \\| || |
 |_  _|| (_) |_  _|
   |_|   \\___/  |_|`}
        </pre>
        <p className="text-xs text-accent-red font-bold mb-2">[ERR] PAGE NOT FOUND</p>
        <p className="text-[10px] text-text-tertiary mb-3">
          the requested path does not exist
        </p>
        <Link
          to="/"
          className="inline-flex items-center justify-center h-7 px-3 border border-accent-green text-accent-green text-[10px] font-bold hover:bg-accent-green hover:text-bg-base transition-colors uppercase"
        >
          [ BACK TO MARKETS ]
        </Link>
      </div>
    </div>
  );
}
