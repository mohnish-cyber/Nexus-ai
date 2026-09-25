import type { AnchorHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { isExternal } from "../../lib/links";

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { href: string; children: ReactNode };

/** Router <Link> for internal paths (including "/#section"), a plain <a> that opens a new tab for external URLs. */
export function SmartLink({ href, children, ...rest }: Props) {
  if (isExternal(href)) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    );
  }
  return (
    <Link to={href} {...rest}>
      {children}
    </Link>
  );
}
