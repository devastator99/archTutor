import Link from "next/link";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/exercise", label: "Exercise" },
  { href: "/drawing", label: "Drawing" },
] as const;

export function Nav() {
  return (
    <header className="border-b border-neutral-200 bg-white">
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
        <Link href="/" className="font-semibold tracking-tight">
          ArchTutor
        </Link>
        <ul className="flex items-center gap-4 text-sm text-neutral-600">
          {LINKS.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="rounded px-2 py-1 hover:bg-neutral-100 hover:text-neutral-900"
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
