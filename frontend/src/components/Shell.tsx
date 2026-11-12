import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../session";
import { Brand } from "./ui";

export function Shell() {
  const { user, companies, company, selectCompany, signOut } = useSession();
  if (!user) return null;

  const links = [
    { to: "/", label: "Accueil", end: true },
    { to: "/parametres/entreprise", label: "Entreprise et modules" },
    ...(user.is_admin
      ? [
          { to: "/parametres/utilisateurs", label: "Utilisateurs" },
          { to: "/parametres/journal", label: "Journal d'activité" },
        ]
      : []),
    { to: "/parametres/compte", label: "Mon compte" },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <Brand />
          {companies.length > 1 && company ? (
            <label className="company-switch">
              <span className="sr-only">Entreprise affichée</span>
              <select value={company.id} onChange={(e) => selectCompany(e.target.value)}>
                {companies.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            company && <p className="company-name">{company.name}</p>
          )}
        </div>
        <nav className="nav" aria-label="Navigation principale">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="who">
            <strong>{user.full_name}</strong>
            <span className="muted">{user.is_admin ? "Administrateur" : user.email}</span>
          </div>
          <button className="btn ghost" onClick={() => void signOut()}>
            Déconnexion
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
