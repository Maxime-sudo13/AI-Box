import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { agentsApi } from "../agents";
import { financeApi } from "../finance";
import { useSession } from "../session";
import { Brand } from "./ui";

export function Shell() {
  const { user, companies, company, selectCompany, signOut, hasModule } = useSession();
  const [alertCount, setAlertCount] = useState(0);
  const [pendingCount, setPendingCount] = useState(0);
  const location = useLocation();
  const companyId = company?.id;
  const financeOn = hasModule("finance");

  // Nombre d'alertes ouvertes, rafraîchi à chaque changement de page.
  useEffect(() => {
    if (!companyId || !financeOn) return setAlertCount(0);
    let cancelled = false;
    financeApi.alerts(companyId).then(
      (r) => !cancelled && setAlertCount(r.items.filter((a) => a.status === "open").length),
      () => {},
    );
    agentsApi.actions(companyId, "pending").then(
      (r) => !cancelled && setPendingCount(r.items.length),
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [companyId, financeOn, location.key]);

  if (!user) return null;

  const finance = hasModule("finance");
  const sections = [
    {
      title: "Pilotage",
      links: [
        { to: "/", label: "Tableau de bord", end: true },
        ...(finance
          ? [
              { to: "/alertes", label: "Alertes", badge: alertCount },
              { to: "/tresorerie", label: "Trésorerie" },
            ]
          : []),
        ...(hasModule("conseiller") ? [{ to: "/conseiller", label: "Conseiller" }] : []),
        ...(finance ? [{ to: "/automatisation", label: "Automatisation", badge: pendingCount }] : []),
        { to: "/donnees", label: "Données" },
        { to: "/connecteurs", label: "Logiciels connectés" },
      ],
    },
    {
      title: "Paramètres",
      links: [
        { to: "/parametres/entreprise", label: "Entreprise et modules" },
        ...(user.is_admin
          ? [
              { to: "/parametres/utilisateurs", label: "Utilisateurs" },
              { to: "/parametres/journal", label: "Journal d'activité" },
            ]
          : []),
        { to: "/parametres/compte", label: "Mon compte" },
      ],
    },
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
          {sections.map((section) => (
            <div key={section.title} className="nav-section">
              <span className="nav-title">{section.title}</span>
              {section.links.map((link) => (
                <NavLink key={link.to} to={link.to} end={"end" in link ? link.end : undefined}>
                  {link.label}
                  {"badge" in link && link.badge ? <span className="nav-badge">{link.badge}</span> : null}
                </NavLink>
              ))}
            </div>
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
