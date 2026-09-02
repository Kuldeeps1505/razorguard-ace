import { NavLink, Outlet } from "react-router-dom";

const links = [
  ["/", "AI Assistant", "✦"],
  ["/consent", "Authorizations", "◌"],
  ["/pipeline", "Transactions", "↔"],
  ["/simulate", "Policy Simulator", "⌁"],
  ["/audit", "Audit Trail", "▤"],
  ["/security", "Security", "◈"],
  ["/merchant", "Merchant Settings", "⚙"],
] as const;

export default function Layout() {
  return (
    <div className="shell">
      <header className="topbar">
        <a className="wordmark" href="/">
          <i>◢</i> Razor<span>Guard</span>
        </a>
        <nav className="topnav" aria-label="Primary">
          <a className="selected" href="/">Control center</a>
          <a href="/pipeline">Payments</a>
          <a href="/merchant">Merchant account</a>
        </nav>
        <div className="top-actions">
          <label className="search"><span>⌕</span><input aria-label="Search" placeholder="Search tools, payments and more" /></label>
          <button className="icon-button" aria-label="Notifications">♧</button>
          <div className="avatar">RG</div>
        </div>
      </header>
      <aside className="nav">
        <div className="nav-label">CONTROL PLANE</div>
        {links.map(([to, label, icon]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            <span className="nav-icon">{icon}</span>{label}
          </NavLink>
        ))}
        <div className="nav-spacer" />
        <div className="mode-card"><span className="mode-dot" /> TEST MODE <button aria-label="Toggle test mode">✓</button></div>
        <a className="help-link" href="/security"><span className="nav-icon">?</span> Help &amp; support</a>
      </aside>
      <main className="main">
        <div className="breadcrumb"><span>RazorGuard</span><b>/</b> Control center</div>
        <Outlet />
      </main>
    </div>
  );
}
