import clsx from "clsx";
import { NavLink } from "react-router-dom";
import { MOBILE_NAV, NAV } from "./nav";

export function MobileNav() {
  const items = NAV.filter((n) => MOBILE_NAV.includes(n.to));
  return (
    <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-line bg-deep/90 backdrop-blur-md pb-[env(safe-area-inset-bottom)]"
      aria-label="Quick navigation">
      <div className="grid grid-cols-5">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"}
            className={({ isActive }) => clsx("flex flex-col items-center gap-1 py-2.5 text-[0.62rem]",
              isActive ? "text-cyan" : "text-dim")}>
            <Icon className="size-5" />
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
